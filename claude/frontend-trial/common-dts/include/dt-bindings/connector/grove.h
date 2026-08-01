/* Grove position indices. A Grove connector is 4 pins: two signal + VCC +
 * GND. The two signal pins are the claimable positions (they double as
 * SCL/SDA on an I2C Grove socket, D(n)/D(n+1) on a digital one — the
 * dual-function copper is discovered at the board binding, not declared here).
 */
#ifndef DT_BINDINGS_CONNECTOR_GROVE_H_
#define DT_BINDINGS_CONNECTOR_GROVE_H_

/* pin 1 (yellow) = SIG0, pin 2 (white) = SIG1, then VCC, GND */
#define GROVE_SIG0	0
#define GROVE_SIG1	1
#define GROVE_VCC	2
#define GROVE_GND	3

#endif
