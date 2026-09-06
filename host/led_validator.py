"""led_validator_strip.py - optical test for an 8-LED WS2812 strip, host side.

Watches 8 LEDs through the webcam. Every LED remembers which of the
colours RED, GREEN, BLUE it has shown so far. Above the strip the number
of LEDs that have shown each colour is displayed ("RED 8/8"); a cell
outline turns green once its LED has shown all three colours. When every
LED has shown every colour, TEST PASSED is shown.

Keys:  +  brighter    -  darker    r  reset    p  print report    q  quit
On quit a report lists every LED that did not show all colours.

Camera automatics (exposure, white balance) are switched off on purpose:
with them on, dimming the LEDs makes the camera brighten the whole image
and the room lighting takes over.

Hue bands in classify() are measured for this camera and this LED strip.
A different webcam sees different hues - re-measure when swapping hardware.
"""

import cv2
import numpy as np

# --- camera setup -----------------------------------------------------------

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)   # 0 = first camera; try 1 if wrong one
assert cap.isOpened(), "no camera"
cap.read()                                  # DirectShow needs one frame before settings

exposure = -12                              # ASSUMPTION: log2 scale; tune with +/-
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # 0.25 = manual on most Windows drivers
cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
cap.set(cv2.CAP_PROP_AUTO_WB, 0)

# --- fixture geometry -------------------------------------------------------

# Where the LED strip lies in the image, as fractions of width / height.
# Tune by eye: every LED must sit inside the circle of its own cell.
STRIP_LEFT, STRIP_RIGHT = 0.15, 0.95
STRIP_TOP, STRIP_BOTTOM = 0.60, 0.76
NUM_LEDS = 8
CIRCLE_RADIUS = 0.3                         # fraction of cell width; only this is measured
MARKER_SIZE = 20                            # px, filled colour box above each cell

# --- constants --------------------------------------------------------------

COLOURS = ["RED", "GREEN", "BLUE"]
MAGENTA = (255, 0, 255)                     # OpenCV colours are (B, G, R)
GREEN = (0, 255, 0)
WHITE = (255, 255, 255)
GREY = (60, 60, 60)
MARKER_COLOUR = {"RED": (0, 0, 255), "GREEN": (0, 255, 0), "BLUE": (255, 0, 0)}
MIN_SATURATION = 60                         # below this: white/grey, no colour
MIN_BRIGHTNESS = 40                         # below this: dark, nothing to classify
FONT = cv2.FONT_HERSHEY_SIMPLEX

# --- colour classification --------------------------------------------------

def classify(roi, mask):
    """Return "RED", "GREEN", "BLUE" or None for the masked part of roi.

    Uses the hue of the mean colour: hue tells *which* colour independent
    of brightness, so an over-exposed LED core does not break the result.
    Hue is on a circle 0..179 (OpenCV scale); red sits at 0 and wraps.
    """
    # Mean colour of the pixels inside the mask (the circle), as B, G, R.
    b, g, r = cv2.mean(roi, mask=mask)[:3]
    # Convert that one mean colour to HSV via a 1x1 image.
    hue, sat, val = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0, 0]

    if val < MIN_BRIGHTNESS or sat < MIN_SATURATION:
        return None                         # too dark or too white to be a colour
    if hue < 15 or hue > 165:               # red, both sides of the wrap
        return "RED"
    if 75 <= hue <= 100:                    # green LED reads as cyan on this camera
        return "GREEN"
    if 105 <= hue <= 130:
        return "BLUE"
    return None                             # some other hue, not one of ours

# --- report -----------------------------------------------------------------

def report(seen):
    """Print every LED that has not shown all colours, with what is missing."""
    failed = [(i, sorted(set(COLOURS) - s)) for i, s in enumerate(seen)
              if len(s) < len(COLOURS)]
    if not failed:
        print(f"all {NUM_LEDS} LEDs showed {', '.join(COLOURS)}")
        return
    print(f"{len(failed)} LED(s) incomplete:")
    for i, missing in failed:
        print(f"  LED {i}: missing {', '.join(missing)}")

# --- main loop --------------------------------------------------------------

seen = [set() for _ in range(NUM_LEDS)]    # per LED: colours it has shown so far

while True:
    ok, frame = cap.read()
    if not ok:
        break

    # Strip rectangle in pixels, then split into NUM_LEDS equal cells.
    height, width = frame.shape[:2]
    left, right = int(width * STRIP_LEFT), int(width * STRIP_RIGHT)
    top, bottom = int(height * STRIP_TOP), int(height * STRIP_BOTTOM)
    cell_w = (right - left) // NUM_LEDS
    cell_h = bottom - top
    radius = int(cell_w * CIRCLE_RADIUS)

    # Circular mask, same for every cell: 255 inside the circle, 0 outside.
    # Only pixels under the 255 area are used by cv2.mean in classify().
    mask = np.zeros((cell_h, cell_w), np.uint8)
    cv2.circle(mask, (cell_w // 2, cell_h // 2), radius, 255, -1)

    labels = []                             # one entry per cell: colour name or None
    for i in range(NUM_LEDS):
        cell_left = left + i * cell_w
        cell_right = cell_left + cell_w
        cx, cy = cell_left + cell_w // 2, top + cell_h // 2   # cell centre

        # Classify first, draw afterwards - drawn lines must not be measured.
        label = classify(frame[top:bottom, cell_left:cell_right], mask)
        labels.append(label)
        if label:
            seen[i].add(label)

        # Cell outline: green once this LED has shown all colours. Plus circle.
        outline = GREEN if len(seen[i]) == len(COLOURS) else MAGENTA
        cv2.rectangle(frame, (cell_left, top), (cell_right, bottom), outline, 1)
        cv2.circle(frame, (cx, cy), radius, MAGENTA, 1)

        # Filled marker above the cell in the detected colour (grey if none).
        my = top - 10 - MARKER_SIZE // 2
        cv2.rectangle(frame, (cx - MARKER_SIZE // 2, my - MARKER_SIZE // 2),
                      (cx + MARKER_SIZE // 2, my + MARKER_SIZE // 2),
                      MARKER_COLOUR.get(label, GREY), -1)

    # Per colour: how many LEDs have shown it at some point. Only goes up.
    best = {c: sum(c in s for s in seen) for c in COLOURS}
    passed = all(best[c] == NUM_LEDS for c in COLOURS)

    # Score lines above the markers, one per colour; TEST PASSED in bold below.
    y = top - MARKER_SIZE - 25 - 30 * len(COLOURS)   # start high enough for all lines
    for c in COLOURS:
        cv2.putText(frame, f"{c} {best[c]}/{NUM_LEDS}", (left, y), FONT, 0.8, WHITE, 1)
        y += 30
    if passed:
        cv2.putText(frame, "TEST PASSED", (left, y), FONT, 0.9, WHITE, 3)

    # Terminal line: exposure, one letter per cell, counts, PASSED flag.
    print(f"exp={exposure}  " + " ".join((l or "-")[0] for l in labels)
          + "  " + " ".join(f"{c[0]}{best[c]}" for c in COLOURS)
          + ("  PASSED" if passed else ""))

    cv2.imshow("led_validator", frame)

    # Keys: q quit (with report), r reset, p report, +/- exposure.
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        report(seen)
        break
    if key == ord("r"):
        seen = [set() for _ in range(NUM_LEDS)]
    if key == ord("p"):
        report(seen)
    if key in (ord("+"), ord("-")):
        exposure += 1 if key == ord("+") else -1
        cap.set(cv2.CAP_PROP_EXPOSURE, exposure)

cap.release()
cv2.destroyAllWindows()