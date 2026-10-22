// SPDX-License-Identifier: GPL-2.0-only
/* Opt-in RAM kernel diagnostic. No ADSP/PAS/SCM or peripheral registers.
 * A manual sysfs request compares the native firmware reader with an allocation
 * owned by this virtual platform device. Never enable in production builds.
 */
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/platform_device.h>
#include <linux/firmware.h>
#include <linux/dma-mapping.h>
#include <linux/crc32.h>
#include <linux/vmalloc.h>
#include <linux/mutex.h>
#include <linux/kobject.h>
#include <linux/sysfs.h>
#include <linux/string.h>
#include <linux/sched.h>
#include <linux/dma-contiguous.h>
#include <linux/io.h>
#include <linux/dma-removed.h>
#include <linux/delay.h>

#define LIMIT (7 * 1024 * 1024)
#define GUARD 64
static struct platform_device *lab_device;
static DEFINE_MUTEX(lab_lock);
static unsigned int attempted;
static bool crc_passed;
static bool dma_passed;
static u64 lab_mask = DMA_BIT_MASK(32);
static char last_result[256] = "Not run; manual crc or dma request required\n";
static u32 byte_table[256];

static u32 byte_crc(const u8 *data, size_t size)
{
	u32 crc = ~0U;
	size_t i;
	for (i = 0; i < size; i++) {
		crc = byte_table[(crc ^ data[i]) & 255] ^ (crc >> 8);
		if (!(i & 0xffff))
			cond_resched();
	}
	return crc ^ ~0U;
}

struct mapping {
	void *allocation;
	dma_addr_t physical;
	size_t size;
	struct dma_attrs attrs;
};

static void *lab_map(phys_addr_t address, size_t size, void *opaque)
{
	struct mapping *m = opaque;
	if (address < m->physical || size > m->size ||
	    address - m->physical > m->size - size)
		return NULL;
	return dma_remap(&lab_device->dev, m->allocation, address, size, &m->attrs);
}

static void lab_unmap(void *address, size_t size, void *opaque)
{
	dma_unremap(&lab_device->dev, address, size);
}

static unsigned int compare(const char *label, const u8 *expected,
			    const u8 *actual, size_t size)
{
	size_t i, first = size, last = 0, differences = 0;
	u32 fast = crc32_le(~0U, actual, size) ^ ~0U;
	u32 slow = byte_crc(actual, size);
	for (i = 0; i < size; i++) {
		if (expected[i] != actual[i]) {
			if (!differences)
				first = i;
			last = i;
			differences++;
		}
		if (!(i & 0xffff))
			cond_resched();
	}
	pr_info("moto-audio-memory: %s n=%zu differences=%zu first=%zu last=%zu fast=%08x byte=%08x\n",
		label, size, differences, first, last, fast, slow);
	if (differences) {
		print_hex_dump(KERN_INFO, "moto-audio-memory: actual ", DUMP_PREFIX_OFFSET,
			       16, 1, actual + first, min_t(size_t, size - first, 256), true);
		pr_info("moto-audio-memory: first expected=%02x actual=%02x; last expected=%02x actual=%02x\n",
			expected[first], actual[first], expected[last], actual[last]);
	}
	return differences || fast != slow;
}

static unsigned int guards(const u8 *data, size_t size)
{
	size_t i;
	for (i = 0; i < GUARD; i++)
		if (data[-GUARD + (long)i] != 0xa5 || data[size + i] != 0xa5)
			return 1;
	return 0;
}

static int run_dma(const struct firmware *fw, bool monitor)
{
	struct mapping m = {0};
	u8 *mapped = NULL, *data, *pattern = NULL, *snapshot = NULL;
	size_t lengths[6] = {4093, 4096, 0, 0, 0, 0};
	size_t i, n;
	unsigned int bad = 0;
	int ret = -ENOMEM;
	m.size = PAGE_ALIGN(PAGE_SIZE + fw->size + 1 + GUARD);
	init_dma_attrs(&m.attrs);
	dma_set_attr(DMA_ATTR_NO_KERNEL_MAPPING, &m.attrs);
	dma_set_attr(DMA_ATTR_SKIP_ZEROING, &m.attrs);
	m.allocation = dma_alloc_attrs(&lab_device->dev, m.size, &m.physical,
				       GFP_KERNEL, &m.attrs);
	if (!m.allocation)
		goto out;
	pr_info("moto-audio-memory: own DMA %pad bytes=%zu allocator=%pf\n",
		&m.physical, m.size, get_dma_ops(&lab_device->dev)->alloc);
	mapped = lab_map(m.physical, m.size, &m);
	if (!mapped)
		goto out;
	pattern = vmalloc(fw->size + 1);
	snapshot = vmalloc(fw->size + 1 + 2 * GUARD);
	if (!pattern || !snapshot)
		goto out;
	for (i = 0; i <= fw->size; i++)
		pattern[i] = (i * 131 + (i >> 8) * 17 + 93) & 255;
	data = mapped + PAGE_SIZE;
	lengths[2] = (4 * 1024 * 1024) - 1;
	lengths[3] = fw->size - 1;
	lengths[4] = fw->size;
	lengths[5] = fw->size + 1;
	for (i = 0; i < ARRAY_SIZE(lengths); i++) {
		n = lengths[i];
		if (n > fw->size + 1)
			continue;
		memset_io(data - GUARD, 0xa5, n + 2 * GUARD);
		memcpy_toio(data, pattern, n);
		lab_unmap(mapped, m.size, &m);
		mapped = lab_map(m.physical, m.size, &m);
		if (!mapped) {
			ret = -ENOMEM;
			goto out;
		}
		data = mapped + PAGE_SIZE;
		memcpy_fromio(snapshot, data - GUARD, n + 2 * GUARD);
		bad |= compare("synthetic IO remap", pattern, snapshot + GUARD, n);
		bad |= guards(snapshot + GUARD, n);
		if (bad) {
			pr_info("moto-audio-memory: synthetic mismatch/guard change; aborting\n");
			ret = -EIO;
			goto out;
		}
		cond_resched();
	}
	memset_io(mapped, 0xa5, m.size);
	lab_unmap(mapped, m.size, &m);
	mapped = NULL;
	/* This vendor API explicitly sets nocache=1. It cannot reuse fw->data. */
	ret = request_firmware_direct("adsp.b04", &lab_device->dev,
				      m.physical + PAGE_SIZE, fw->size,
				      lab_map, lab_unmap, &m);
	if (ret != fw->size) {
		if (ret >= 0)
			ret = -EIO;
		goto out;
	}
	mapped = lab_map(m.physical, m.size, &m);
	if (!mapped) {
		ret = -ENOMEM;
		goto out;
	}
	data = mapped + PAGE_SIZE;
	memcpy_fromio(snapshot, data - GUARD, fw->size + 2 * GUARD);
	bad |= compare("firmware direct IO read", fw->data, snapshot + GUARD, fw->size);
	bad |= guards(snapshot + GUARD, fw->size);
	if (!bad && monitor) {
		/* A bounded hold detects asynchronous writes after a verified load. */
		for (i = 0; i < 20; i++) {
			pr_info("moto-audio-memory: hold %zu verified firmware remains allocated\n", i);
			msleep(100);
			memcpy_fromio(snapshot, data - GUARD, fw->size + 2 * GUARD);
			bad |= compare("firmware held IO read", fw->data, snapshot + GUARD, fw->size);
			bad |= guards(snapshot + GUARD, fw->size);
			if (bad)
				break;
		}
	}
	ret = bad ? -EIO : 0;
out:
	if (mapped)
		lab_unmap(mapped, m.size, &m);
	vfree(pattern);
	vfree(snapshot);
	if (m.allocation)
		dma_free_attrs(&lab_device->dev, m.size, m.allocation, m.physical, &m.attrs);
	return ret;
}

static int run_pil_dma(const struct firmware *fw)
{
	struct device *source;
	struct cma *previous_area = lab_device->dev.cma_area;
	const struct dma_map_ops *previous_ops = get_dma_ops(&lab_device->dev);
	int ret;
	source = bus_find_device_by_name(&platform_bus_type, NULL, "c200000.qcom,lpass");
	if (!source)
		return -ENODEV;
	if (!source->cma_area || get_dma_ops(source) != &removed_dma_ops ||
	    !removed_dma_ops.alloc || !removed_dma_ops.free ||
	    !removed_dma_ops.remap || !removed_dma_ops.unremap) {
		put_device(source);
		return -ENODEV;
	}
	/* The virtual device owns its allocation. Never reuse PIL's allocation,
	 * change the actual device, use a fixed address or call its driver. */
	lab_device->dev.cma_area = source->cma_area;
	set_dma_ops(&lab_device->dev, get_dma_ops(source));
	pr_info("moto-audio-memory: virtual allocation using PIL pool/backend; no subsystem request\n");
	ret = run_dma(fw, true);
	set_dma_ops(&lab_device->dev, previous_ops);
	lab_device->dev.cma_area = previous_area;
	put_device(source);
	return ret;
}

static ssize_t run_store(struct kobject *object, struct kobj_attribute *attribute,
			 const char *buffer, size_t count)
{
	const struct firmware *fw = NULL;
	bool pil = sysfs_streq(buffer, "pil-dma");
	bool dma = sysfs_streq(buffer, "dma") || pil;
	unsigned int bit = pil ? 4 : dma ? 2 : 1;
	u32 fast, slow;
	int ret;
	if (!dma && !sysfs_streq(buffer, "crc"))
		return -EINVAL;
	if (!mutex_trylock(&lab_lock))
		return -EBUSY;
	if (attempted & bit) {
		ret = -EALREADY;
		goto out;
	}
	if (dma && !crc_passed) {
		ret = -EPERM;
		goto out;
	}
	if (pil && !dma_passed) {
		ret = -EPERM;
		goto out;
	}
	attempted |= bit;
	ret = request_firmware(&fw, "adsp.b04", &lab_device->dev);
	if (ret)
		goto out;
	if (fw->size < 4096 || fw->size > LIMIT) {
		ret = -EFBIG;
		goto out;
	}
	fast = crc32_le(~0U, fw->data, fw->size) ^ ~0U;
	slow = byte_crc(fw->data, fw->size);
	pr_info("moto-audio-memory: firmware cached n=%zu fast=%08x byte=%08x\n", fw->size, fast, slow);
	if (fast != slow) {
		crc_passed = false;
		ret = -EIO;
		goto out;
	}
	ret = pil ? run_pil_dma(fw) : dma ? run_dma(fw, false) : 0;
	if (!dma)
		crc_passed = !ret;
	if (dma && !pil)
		dma_passed = !ret;
out:
	release_firmware(fw);
	scnprintf(last_result, sizeof(last_result), "%s completed result=%d; see moto-audio-memory kernel log\n",
		  pil ? "pil-dma" : dma ? "dma" : "crc", ret);
	pr_info("moto-audio-memory: %s", last_result);
	mutex_unlock(&lab_lock);
	return ret ? ret : count;
}

static ssize_t result_show(struct kobject *object, struct kobj_attribute *attribute,
			   char *buffer)
{
	ssize_t size;
	mutex_lock(&lab_lock);
	size = scnprintf(buffer, PAGE_SIZE, "%s", last_result);
	mutex_unlock(&lab_lock);
	return size;
}

static struct kobj_attribute run_attribute = __ATTR(run, 0200, NULL, run_store);
static struct kobj_attribute result_attribute = __ATTR(result, 0444, result_show, NULL);
static struct attribute *attributes[] = { &run_attribute.attr, &result_attribute.attr, NULL };
static struct attribute_group group = { .attrs = attributes };

static int __init lab_init(void)
{
	struct kobject *object;
	unsigned int i, j;
	u32 crc;
	int ret;
	for (i = 0; i < ARRAY_SIZE(byte_table); i++) {
		crc = i;
		for (j = 0; j < 8; j++)
			crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320U : 0);
		byte_table[i] = crc;
	}
	lab_device = platform_device_register_simple("moto-audio-memory", -1, NULL, 0);
	if (IS_ERR(lab_device))
		return PTR_ERR(lab_device);
	lab_device->dev.dma_mask = &lab_mask;
	lab_device->dev.coherent_dma_mask = lab_mask;
	object = kobject_create_and_add("moto_audio_memory", kernel_kobj);
	if (!object) {
		platform_device_unregister(lab_device);
		return -ENOMEM;
	}
	ret = sysfs_create_group(object, &group);
	if (ret) {
		kobject_put(object);
		platform_device_unregister(lab_device);
	}
	return ret;
}
device_initcall(lab_init);
