// SPDX-License-Identifier: MIT
/* Return the running native Linux system to the Motorola bootloader. */
#include <linux/reboot.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(void)
{
    sync();
    if (syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
                LINUX_REBOOT_CMD_RESTART2, "bootloader") < 0) {
        perror("reboot to bootloader");
        return 1;
    }
    return 0;
}
