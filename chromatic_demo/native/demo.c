/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdint.h>
#include <stdio.h>
#include "assets.h"

uint8_t selected = 0;
uint8_t current_page = 0;
uint8_t in_dialogue = 0;

static void text_at(uint8_t x, uint8_t y, const char *text) {
    while (*text) {
        gotoxy(x++, y);
        setchar(*text++);
    }
}

static void clear_rows(uint8_t first, uint8_t last) {
    uint8_t row;
    for (row = first; row <= last; row++) {
        text_at(0, row, "                    ");
    }
}

static void scene(void) {
    clear_rows(0, 17);
    text_at(1, 0, "TUXEMON PROTOTYPE");
    text_at(1, 1, PROVIDER_LABEL);
    set_bkg_tiles(3, 3, 2, 4, professor_map);
    set_bkg_tiles(11, 3, 2, 4, rockitten_map);
    text_at(1, 7, "Professor Rockitten");
    text_at(1, 8, "------------------");
}

static void menu(void) {
    uint8_t index;
    in_dialogue = 0;
    clear_rows(9, 17);
    for (index = 0; index < INTENT_COUNT; index++) {
        text_at(1, 10 + 2 * index, index == selected ? "X" : " ");
        text_at(3, 10 + 2 * index, intent_labels[index]);
    }
    text_at(1, 16, "UP/DOWN: CHOOSE");
    text_at(1, 17, "A: TALK  B: BACK");
}

static void dialogue(void) {
    uint8_t line;
    in_dialogue = 1;
    clear_rows(9, 17);
    for (line = 0; line < PAGE_LINES; line++) {
        text_at(1, 9 + line, dialogue_pages[selected][current_page][line]);
    }
    text_at(1, 16, current_page + 1 < page_counts[selected]
            ? "A: NEXT  B: BACK" : "A: DONE  B: BACK");
    text_at(1, 17, SNAPSHOT_LABEL);
}

void main(void) {
    uint8_t previous = 0;
    uint8_t pressed;
    uint8_t keys;
    const palette_color_t palette[] = {
        RGB(31, 31, 28), RGB(23, 25, 20),
        RGB(10, 14, 12), RGB(1, 4, 5)
    };
    DISPLAY_OFF;
    font_init();
    font_load(font_min);
    set_bkg_data(128, ART_TILE_COUNT, art_tiles);
    BGP_REG = 0xe4;
    if (_cpu == CGB_TYPE) set_bkg_palette(0, 1, palette);
    scene();
    menu();
    SHOW_BKG;
    DISPLAY_ON;
    while (1) {
        wait_vbl_done();
        keys = joypad();
        pressed = keys & ~previous;
        previous = keys;
        if (pressed & J_B) {
            menu();
        } else if (in_dialogue) {
            if (pressed & J_A) {
                if (++current_page < page_counts[selected]) dialogue();
                else menu();
            }
        } else if (pressed & J_UP) {
            selected = selected ? selected - 1 : INTENT_COUNT - 1;
            menu();
        } else if (pressed & J_DOWN) {
            selected = (selected + 1) % INTENT_COUNT;
            menu();
        } else if (pressed & J_A) {
            current_page = 0;
            dialogue();
        }
    }
}
