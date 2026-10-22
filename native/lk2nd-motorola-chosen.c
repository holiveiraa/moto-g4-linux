// SPDX-License-Identifier: BSD-3-Clause
// Preserve firmware-selected hardware on the Athene downstream kernel.
#include <boot.h>
#include <debug.h>
#include <dev_tree.h>
#include <libfdt.h>
#include <stdlib.h>
#include <string.h>
#include "device.h"

static struct {
    const char *name;
    void *data;
    int size;
} properties[] = {
    { "linux,hwrev", NULL, 0 },
    { "linux,seriallow", NULL, 0 },
    { "linux,serialhigh", NULL, 0 },
    { "mmi,powerup_reason", NULL, 0 },
    { "mmi,mbmversion", NULL, 0 },
    { "mmi,boot_seq", NULL, 0 },
    { "mmi,prod_id", NULL, 0 },
    { "mmi,msm_hw", NULL, 0 },
    { "mmi,panel_name", NULL, 0 },
    { "mmi,panel_ver", NULL, 0 },
    { "mmi,display_auto_detect", NULL, 0 },
    { "mmi,battid", NULL, 0 },
    { "mmi,nfc", NULL, 0 },
    { "mmi,imager", NULL, 0 },
    { "mmi,fps", NULL, 0 },
    { "mmi,dtv", NULL, 0 },
    { "mmi,baseband", NULL, 0 },
};

void moto_cache_chosen(const void *dtb)
{
    int chosen, length, count = 0;
    unsigned i;
    const void *value;
    if (!dtb || !lk2nd_dev.device || strncmp(lk2nd_dev.device, "athene", 6))
        return;
    chosen = fdt_path_offset(dtb, "/chosen");
    if (chosen < 0)
        return;
    for (i = 0; i < sizeof(properties) / sizeof(properties[0]); ++i) {
        value = fdt_getprop(dtb, chosen, properties[i].name, &length);
        if (!value || length <= 0 || length > 512)
            continue;
        properties[i].data = malloc(length);
        ASSERT(properties[i].data);
        memcpy(properties[i].data, value, length);
        properties[i].size = length;
        ++count;
    }
    dprintf(INFO, "Athene: cached %d firmware-selected /chosen fields\n", count);
}

static int moto_forward_chosen(void *dtb, const char *cmdline, enum boot_type type)
{
    unsigned i;
    int chosen, ret, count = 0;
    (void)cmdline;
    (void)type;
    if (!properties[0].data && !properties[8].data)
        return 0;
    chosen = fdt_path_offset(dtb, "/chosen");
    if (chosen < 0)
        return chosen;
    for (i = 0; i < sizeof(properties) / sizeof(properties[0]); ++i) {
        if (!properties[i].data)
            continue;
        ret = fdt_setprop(dtb, chosen, properties[i].name,
                          properties[i].data, properties[i].size);
        if (ret < 0) {
            dprintf(CRITICAL, "Athene: cannot forward %s: %d\n", properties[i].name, ret);
            return ret;
        }
        ++count;
    }
    dprintf(INFO, "Athene: forwarded %d firmware-selected /chosen fields\n", count);
    return 0;
}
DEV_TREE_UPDATE(moto_forward_chosen);
