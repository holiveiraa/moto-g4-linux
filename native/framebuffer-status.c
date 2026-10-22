/* SPDX-License-Identifier: MIT
 * Diagnostic userspace drawing through the vendor fbdev driver, without fbcon.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

struct glyph { char letter; uint8_t rows[7]; };
static const struct glyph glyphs[] = {
    {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
    {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
    {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
    {'G',{14,17,16,23,17,17,14}}, {'H',{17,17,17,31,17,17,17}},
    {'I',{14,4,4,4,4,4,14}}, {'J',{7,2,2,2,2,18,12}},
    {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
    {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
    {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
    {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
    {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
    {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
    {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
    {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
    {'4',{2,6,10,18,31,2,2}}, {':',{0,4,4,0,4,4,0}}
};
static struct fb_fix_screeninfo fixed;
static struct fb_var_screeninfo variable;
static uint8_t *pixels;

static uint32_t component(unsigned value, struct fb_bitfield field)
{
    if (!field.length) return 0;
    return ((value * ((1U << field.length) - 1) + 127) / 255) << field.offset;
}
static uint32_t colour(unsigned red, unsigned green, unsigned blue)
{
    return component(red, variable.red) | component(green, variable.green) |
           component(blue, variable.blue) | component(255, variable.transp);
}
static void pixel(unsigned x, unsigned y, uint32_t value)
{
    if (x < variable.xres && y < variable.yres)
        memcpy(pixels + y * fixed.line_length + x * 4, &value, 4);
}
static void text(const char *value, unsigned y, unsigned scale, uint32_t ink)
{
    size_t count = strlen(value);
    if (count * 6 * scale > variable.xres) return;
    unsigned left = (variable.xres - count * 6 * scale) / 2;
    for (size_t n = 0; n < count; ++n) {
        for (size_t g = 0; g < sizeof(glyphs)/sizeof(glyphs[0]); ++g) {
            if (glyphs[g].letter != value[n]) continue;
            for (unsigned row = 0; row < 7; ++row)
                for (unsigned col = 0; col < 5; ++col)
                    if (glyphs[g].rows[row] & (16 >> col))
                        for (unsigned sy = 0; sy < scale; ++sy)
                            for (unsigned sx = 0; sx < scale; ++sx)
                                pixel(left + (n * 6 + col) * scale + sx,
                                      y + row * scale + sy, ink);
        }
    }
}
int main(int argc, char **argv)
{
    int fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) { perror("open fb0"); return 1; }
    if (ioctl(fd, FBIOGET_FSCREENINFO, &fixed) < 0 ||
        ioctl(fd, FBIOGET_VSCREENINFO, &variable) < 0) {
        perror("framebuffer geometry"); close(fd); return 1;
    }
    fprintf(stderr, "fb0: %ux%u virtual=%ux%u bpp=%u stride=%u\n",
            variable.xres, variable.yres, variable.xres_virtual,
            variable.yres_virtual, variable.bits_per_pixel, fixed.line_length);
    if (argc != 2 || strcmp(argv[1], "--paint")) { close(fd); return 0; }
    if (variable.bits_per_pixel != 32 || variable.xres < 320 ||
        variable.yres < 640 || variable.xres > 8192 || variable.yres > 8192 ||
        variable.yres_virtual < variable.yres || variable.yres_virtual > 16384 ||
        fixed.line_length < variable.xres * 4 || fixed.line_length > 131072) {
        fprintf(stderr, "Unsupported framebuffer geometry\n"); close(fd); return 1;
    }
    struct fb_bitfield fields[] = {variable.red, variable.green, variable.blue, variable.transp};
    for (unsigned n = 0; n < 4; ++n)
        if (fields[n].length > 8 || fields[n].offset + fields[n].length > 32) {
            fprintf(stderr, "Unsupported pixel layout\n"); close(fd); return 1;
        }
    size_t length = (size_t)fixed.line_length * variable.yres_virtual;
    if (length > 128U * 1024U * 1024U) { close(fd); return 1; }
    pixels = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (pixels == MAP_FAILED) { perror("mmap framebuffer"); close(fd); return 1; }
    fprintf(stderr, "Framebuffer mapped: %zu bytes\n", length);
    uint32_t background = colour(12, 20, 32);
    for (unsigned y = 0; y < variable.yres; ++y)
        for (unsigned x = 0; x < variable.xres; ++x) pixel(x, y, background);
    unsigned scale = variable.xres / 110;
    if (scale < 2) scale = 2;
    unsigned y = variable.yres / 5;
    text("MOTO G4", y, scale + 2, colour(240, 245, 255));
    text("LINUX NATIVO", y + 14 * scale, scale, colour(75, 215, 170));
    text("USB SSH: OK", y + 29 * scale, scale, colour(240, 245, 255));
    text("MODO DE TESTE", y + 44 * scale, scale, colour(160, 180, 205));
    variable.xoffset = variable.yoffset = 0;
    if (ioctl(fd, FBIOBLANK, FB_BLANK_UNBLANK) < 0) perror("unblank");
    if (ioctl(fd, FBIOPAN_DISPLAY, &variable) < 0) perror("pan display");
    fprintf(stderr, "Status drawn; physical panel output still requires observation\n");
    munmap(pixels, length);
    close(fd);
    return 0;
}
