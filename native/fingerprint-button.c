// SPDX-License-Identifier: MIT
/* Native button service for the Moto G4 Plus FPC sensor.
 * ARM32 OEM ABI only. No images, biometric templates, enrollment or database.
 * Detection commands reuse the owner's original FPC/QSEE libraries/firmware.
 * Stock HAL call order was inspected locally: qualification 3 = finger;
 * 2/4 = retry and 8 = qualification busy. Never treat a bare IRQ as a tap.
 */
extern void *dlopen(const char *, int);
extern void *dlsym(void *, const char *);
extern char *dlerror(void);
extern int printf(const char *, ...);
extern int puts(const char *);
extern void exit(int) __attribute__((noreturn));
extern int fflush(void *);
extern int usleep(unsigned);
extern int open(const char *, int, ...);
extern int read(int, void *, unsigned);
extern int write(int, const void *, unsigned);
extern int close(int);
extern long lseek(int, long, int);
extern int poll(void *, unsigned, int);
extern void *signal(int, void (*)(int));
extern int socket(int, int, int);
extern int sendto(int, const void *, unsigned, int, const void *, unsigned);
extern int clock_gettime(int, void *);
struct poll_fd { int fd; short events, revents; };
struct local_address { unsigned short family; char path[108]; };
struct clock_time { long seconds, nanoseconds; };
static volatile int running = 1;
static volatile int dump = 0;
static void stop(int sig) { (void)sig; running = 0; }
static void statistics(int sig) { (void)sig; dump = 1; }
static unsigned long millis(void) {
    struct clock_time t;
    clock_gettime(1, &t);
    return (unsigned long)t.seconds * 1000UL + (unsigned long)t.nanoseconds / 1000000UL;
}
static void *sym(void *library, const char *name) {
    void *p = dlsym(library, name);
    if (!p) { printf("Missing %s: %s\n", name, dlerror()); exit(2); }
    return p;
}
static int wait_interrupt(void) {
    /* Reopen after each notification, as the OEM driver expects. A deadline
     * allows SIGTERM and normal service shutdown while no finger is present. */
    int fd = open("/sys/bus/spi/devices/spi7.0/irq", 0x800);
    char level = '0';
    if (fd < 0) return -1;
    if (read(fd, &level, 1) != 1) { close(fd); return -1; }
    if (level == '1') { close(fd); return 1; }
    struct poll_fd p = { fd, 2 | 8, 0 }; /* POLLPRI | POLLERR */
    int status = poll(&p, 1, 1000);
    /* A sysfs notification may describe a deassertion. The pin level, not
     * POLLERR/POLLPRI alone, decides whether the secure sensor has data. */
    if (status > 0) {
        lseek(fd, 0, 0);
        level = '0';
        status = read(fd, &level, 1) == 1 && level == '1';
        if (!status) usleep(10000);
    }
    close(fd);
    return status > 0 ? 1 : 0;
}
static void notify(int fd, const char *message, unsigned length) {
    struct local_address address = { 1, "/run/moto-ux.sock" };
    sendto(fd, message, length, 0, &address, sizeof(address));
}
static int run(void) {
    void *lib = dlopen("lib_fpc_tac_shared.so", 2), *tac = 0, *device;
    if (!lib) { puts(dlerror()); return 2; }
    int (*init)(const char *, void **) = sym(lib, "fpc_tac_init");
    int (*open_tac)(void *) = sym(lib, "fpc_tac_open");
    int (*wake)(void *) = sym(lib, "fpc_tac_wakeup_setup");
    int (*qualify)(void *) = sym(lib, "fpc_tac_wakeup_qualification");
    int (*fingerup)(void *) = sym(lib, "fpc_tac_fingerup_setup");
    int (*sleep_tac)(void *) = sym(lib, "fpc_tac_deep_sleep");
    int (*close_tac)(void *) = sym(lib, "fpc_tac_close");
    void *(*new_device)(void) = sym(lib, "fpc_ree_device_new");
    void (*destroy)(void *) = sym(lib, "fpc_ree_device_destroy");
    int (*clock_enabled)(void *, int) = sym(lib, "fpc_ree_device_set_clock_enabled");
    int (*device_enabled)(void *, int) = sym(lib, "fpc_ree_device_set_device_enabled");
    device = new_device();
    if (!device) { puts("FPC sysfs device unavailable"); return 3; }
    if (clock_enabled(device, 1)) return 4;
    int status = init("fpctzappfingerprint", &tac);
    if (!status) status = open_tac(tac);
    if (status) { printf("FPC startup failed: %d\n", status); clock_enabled(device, 0); return 5; }
    /* The OEM HAL parks the sensor after open before arming its worker. This
     * is a real device-state transition, separate from closing the SPI clock. */
    status = sleep_tac(tac);
    if (status) { printf("FPC initial sleep failed: %d\n", status); clock_enabled(device, 0); return 5; }
    clock_enabled(device, 0);
    usleep(1000);
    clock_enabled(device, 1);
    /* Motorola's "device enabled" flag clips a 160x44 area at the bottom of
     * the touchscreen. Apply it only during an actual qualified contact,
     * rather than leaving a permanent dead zone in the software space bar. */
    device_enabled(device, 0);
    signal(15, stop); signal(2, stop); signal(10, statistics);
    int transport = socket(1, 2, 0);
    unsigned taps = 0, errors = 0;
    unsigned counts[16] = {0};
    puts("FPC detection ready; waiting for a physical finger. No biometric data collected."); fflush(0);
    while (running) {
        if (dump) {
            printf("FPC qualification counts: retry2=%u finger3=%u retry4=%u busy8=%u, taps=%u\n", counts[2], counts[3], counts[4], counts[8], taps);
            fflush(0); dump=0;
        }
        if (wake(tac)) { errors++; break; }
        clock_enabled(device, 0);
        int irq = 0;
        while (running && !irq) irq = wait_interrupt();
        clock_enabled(device, 1);
        if (!running) break;
        if (irq < 0) { errors++; break; }
        status = qualify(tac);
        if (status >= 0 && status < 16) counts[status]++;
        for (int retry=0; running && status==8 && retry<5; retry++) {
            usleep(1000); status=qualify(tac);
        }
        if (status == 2 || status == 4) { usleep(250000); continue; }
        if (status != 3) { printf("FPC qualification status: %d\n", status); errors++; break; }
        device_enabled(device, 1);
        unsigned long down = millis();
        if (fingerup(tac)) { errors++; break; }
        clock_enabled(device, 0);
        irq = 0;
        while (running && !irq) irq = wait_interrupt();
        clock_enabled(device, 1);
        device_enabled(device, 0);
        if (!running) break;
        if (irq < 0) { errors++; break; }
        unsigned long duration = millis() - down;
        if (duration >= 40) {
            notify(transport, duration >= 800 ? "front-hold" : "home", duration >= 800 ? 10 : 4);
            printf("FPC physical tap %u (%lu ms)\n", ++taps, duration); fflush(0);
            usleep(150000); /* debounce without repeat when held */
        }
    }
    clock_enabled(device, 1);
    device_enabled(device, 0);
    sleep_tac(tac);
    close_tac(tac);
    clock_enabled(device, 0);
    destroy(device);
    close(transport);
    printf("FPC stopped; %u taps, %u errors\n", taps, errors); fflush(0);
    return errors ? 6 : 0;
}
void _start(void) { exit(run()); }
