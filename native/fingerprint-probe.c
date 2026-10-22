// SPDX-License-Identifier: MIT
/* Minimal, explicit read-only experiment for the stock FPC vendor ABI.
 * No enrolment, authentication database, templates, images, or key changes.
 * Uses only detection setup/qualification and the owner's original library.
 * Stock ARM32 Bionic ABI; no Android OS/service is launched.
 */
extern void *dlopen(const char *, int);
extern void *dlsym(void *, const char *);
extern char *dlerror(void);
extern int printf(const char *, ...);
extern int puts(const char *);
extern void exit(int) __attribute__((noreturn));
extern int fflush(void *);
extern int usleep(unsigned);

static void *symbol(void *library, const char *name) {
    void *p = dlsym(library, name);
    if (!p) { printf("Missing %s: %s\n", name, dlerror()); exit(2); }
    return p;
}

static int run(void) {
    void *lib = dlopen("lib_fpc_tac_shared.so", 2);
    void *tac = 0;
    int status;
    if (!lib) { puts(dlerror()); return 2; }
    int (*init)(const char *, void **) = symbol(lib, "fpc_tac_init");
    int (*open_tac)(void *) = symbol(lib, "fpc_tac_open");
    int (*wake)(void *) = symbol(lib, "fpc_tac_wakeup_setup");
    int (*qualify)(void *) = symbol(lib, "fpc_tac_wakeup_qualification");
    int (*sleep_tac)(void *) = symbol(lib, "fpc_tac_deep_sleep");
    int (*close_tac)(void *) = symbol(lib, "fpc_tac_close");
    int (*sensor_info)(void *, unsigned char *, unsigned char *) = symbol(lib, "fpc_tac_get_sensor_info");
    int (*selftest)(void *, unsigned *) = symbol(lib, "fpc_tac_selftest");
    status = init("fpctzappfingerprint", &tac);
    printf("fpc init: %d\n", status); fflush(0);
    if (status || !tac) return 3;
    status = open_tac(tac);
    printf("fpc open: %d\n", status); fflush(0);
    if (status) return 4;
    unsigned char width=0, height=0;
    unsigned diagnostics=0;
    printf("sensor info: %d", sensor_info(tac, &width, &height));
    printf(" (%u x %u)\n", width, height); fflush(0);
    printf("sensor selftest: %d", selftest(tac, &diagnostics));
    printf(" (diagnostics %u)\n", diagnostics); fflush(0);
    status = wake(tac);
    printf("fpc detect setup: %d\n", status); fflush(0);
    if (!status) {
        /* Only 20 polls; does not read an image or enroll a fingerprint. */
        for (int i=0; i<20; i++) {
            usleep(100000);
            printf("detection status: %d\n", qualify(tac)); fflush(0);
        }
    }
    printf("fpc sleep: %d\n", sleep_tac(tac));
    printf("fpc close: %d\n", close_tac(tac));
    fflush(0);
    return status ? 5 : 0;
}

/* The loader has already initialized Bionic. Avoid cross-toolchain glibc CRT. */
void _start(void) { exit(run()); }
