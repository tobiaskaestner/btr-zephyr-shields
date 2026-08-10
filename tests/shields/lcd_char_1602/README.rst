LCD Char 1602 Shield Testing
#############################

Generic 16x2 character LCD (HD44780-class, 4-bit parallel GPIO), one of
two shields declared by a single ``shields:`` list in
``boards/shields/arduino_lcd/`` (shield-plurality-brief.md Sec 5's corpus
example) -- a folder named neither ``lcd_char_1602`` nor its sibling
``lcd_tft_24``. Both target boards offer exactly one ``arduino-r3``
socket, so promotion needs no explicit ``socket=``. No required
parameters, so the bare shield name promotes unassisted.
