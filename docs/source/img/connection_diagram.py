#####################################################################
#                                                                   #
# /docs/source/img/connection_diagram.py                            #
#                                                                   #
# Copyright 2026, JQI                                               #
# Author: Ian Spielman                                              #
#                                                                   #
# This file is part of labscript, in the labscript suite            #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################
"""Draw connection_diagram.png, the example connection table in the docs.

Run from this directory: python connection_diagram.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

NAME_COLOURS = {
    "device": "#6a2c91",
    "pseudoclock": "#1f5fa8",
    "clockline": "#167a6e",
    "intermediate": "#b3121b",
    "output": "#4c8c2b",
}
TYPE_COLOUR = "#c0601a"
LINK_COLOUR = "#5b9bd5"
BOX_HEIGHT = 1.1

fig, ax = plt.subplots(figsize=(26, 15.7))
ax.set_xlim(0, 26)
ax.set_ylim(-0.2, 15.5)
ax.axis("off")
renderer = fig.canvas.get_renderer()


def centred_type(x, y, type_name):
    """Write "Type: <type_name>", centred on x, with the type in colour."""
    label = ax.text(x, y, "Type: ", ha="left", va="center", fontsize=14)
    value = ax.text(x, y, type_name, ha="left", va="center", fontsize=14,
                    color=TYPE_COLOUR)
    to_data = ax.transData.inverted()
    widths = [
        to_data.transform((t.get_window_extent(renderer).width, 0))[0]
        - to_data.transform((0, 0))[0]
        for t in (label, value)
    ]
    start = x - sum(widths) / 2
    label.set_x(start)
    value.set_x(start + widths[0])


def box(x, y, width, name, kind, type_name, note=None):
    """Draw a device box centred on (x, y); return its top and bottom centres."""
    height = BOX_HEIGHT + (0.4 if note else 0)
    ax.add_patch(
        FancyBboxPatch(
            (x - width / 2, y - height / 2), width, height,
            boxstyle="round,pad=0.02,rounding_size=0.25",
            facecolor="white", edgecolor="black", linewidth=1.6,
        )
    )
    top = y + height / 2
    ax.text(x, top - 0.38, name, ha="center", va="center", fontsize=17,
            color=NAME_COLOURS[kind])
    centred_type(x, top - 0.82, type_name)
    if note:
        ax.text(x, top - 1.22, note, ha="center", va="center", fontsize=12,
                style="italic")
    return (x, top), (x, y - height / 2)


def link(child_top, parent_bottom, label, dashed=False):
    """An arrow from a child up to its parent, labelled with the connection."""
    ax.annotate(
        "", xy=parent_bottom, xytext=child_top,
        arrowprops=dict(arrowstyle="-|>", color=LINK_COLOUR, lw=2.2,
                        linestyle="--" if dashed else "-", mutation_scale=22),
    )
    mid_x = (child_top[0] + parent_bottom[0]) / 2
    mid_y = (child_top[1] + parent_bottom[1]) / 2
    # On the side of the link away from the parent, so the label clears the line:
    left = child_top[0] < parent_bottom[0]
    ax.text(mid_x + (-0.15 if left else 0.15), mid_y + 0.1, label,
            ha="right" if left else "left", va="bottom", fontsize=13,
            color=LINK_COLOUR)


def channels(parent_bottom, x, outputs):
    """Stack a device's channels below it, each linked by its connection."""
    spine = x - 1.9
    y = parent_bottom[1] - 1.2
    for name, type_name, connection in outputs:
        (_, top), _ = box(spine + 1.45 + 3.3 / 2, y, 3.3, name, "output", type_name)
        left = spine + 1.45
        ax.plot([spine, left], [y, y], color=LINK_COLOUR, lw=2.2)
        ax.text(spine + 0.1, y + 0.18, connection, ha="left", va="bottom",
                fontsize=12, color=LINK_COLOUR)
        last = y
        y -= 1.45
    ax.annotate(
        "", xy=(spine, parent_bottom[1]), xytext=(spine, last),
        arrowprops=dict(arrowstyle="-|>", color=LINK_COLOUR, lw=2.2,
                        mutation_scale=22),
    )


# The master pseudoclock device and its tree
_, pb_bottom = box(9.5, 14.3, 4.2, "pulseblaster_0", "device",
                   "PulseBlaster", "PseudoclockDevice, master")
pc_top, pc_bottom = box(9.5, 11.9, 4.6, "pulseblaster_0.pseudoclock",
                        "pseudoclock", "Pseudoclock")
link(pc_top, pb_bottom, "clock")
fast_top, fast_bottom = box(5.2, 9.4, 3.6, "fast_clock", "clockline", "ClockLine")
slow_top, slow_bottom = box(13.8, 9.4, 3.6, "slow_clock", "clockline",
                            "ClockLine", "ramping_allowed=False")
link(fast_top, pc_bottom, "flag 0")
link(slow_top, pc_bottom, "flag 1")

ni0_top, ni0_bottom = box(2.4, 6.7, 3.8, "ni_card_0", "intermediate",
                          "NI_PCIe_6363")
ni1_top, ni1_bottom = box(8.0, 6.7, 3.8, "ni_card_1", "intermediate",
                          "NI_PCI_6733")
nt1_top, nt1_bottom = box(13.8, 6.7, 4.2, "novatech_DDS9m_1", "intermediate",
                          "NovaTechDDS9M")
link(ni0_top, fast_bottom, "internal")
link(ni1_top, fast_bottom, "internal")
link(nt1_top, slow_bottom, "internal")

channels(ni0_bottom, 2.4, [
    ("switch_1", "DigitalOut", "port0/line1"),
    ("MOT_coil", "AnalogOut", "ao0"),
    ("MOT_fluorescence", "AnalogIn", "ai3"),
])
channels(ni1_bottom, 8.0, [
    ("bias_coil_x", "AnalogOut", "ao0"),
    ("bias_coil_y", "AnalogOut", "ao1"),
    ("bias_coil_z", "AnalogOut", "ao2"),
])
channels(nt1_bottom, 13.8, [
    ("source_MOT_AOM", "DDS", "channel 0"),
    ("rf_knife", "DDS", "channel 1"),
    ("laser_offset_AOM", "StaticDDS", "channel 2"),
    ("imaging_AOM", "StaticDDS", "channel 3"),
])

# A secondary pseudoclock device, triggered by the master
prawn_top, prawn_bottom = box(21.2, 14.3, 4.2, "prawnblaster_0", "device",
                              "PrawnBlaster", "PseudoclockDevice, secondary")
link((pb_bottom[0] + 2.1, 14.1), (prawn_top[0] - 2.1, 14.1), "", dashed=True)
ax.text(15.35, 14.32, "trigger: flag 3 of pulseblaster_0", ha="center",
        va="bottom", fontsize=13, color=LINK_COLOUR)
ppc_top, ppc_bottom = box(21.2, 11.9, 5.0, "prawnblaster_0_pseudoclock_0",
                          "pseudoclock", "Pseudoclock")
link(ppc_top, prawn_bottom, "pseudoclock 0")
pcl_top, pcl_bottom = box(21.2, 9.4, 4.8, "prawnblaster_0_clock_line_0",
                          "clockline", "ClockLine")
link(pcl_top, ppc_bottom, "GPIO 9")
nt2_top, nt2_bottom = box(21.2, 6.7, 4.2, "novatech_DDS9m_2", "intermediate",
                          "NovaTechDDS9M")
link(nt2_top, pcl_bottom, "internal")
channels(nt2_bottom, 21.2, [
    ("dipole_trap_AOM", "DDS", "channel 0"),
    ("repump_AOM", "DDS", "channel 1"),
])

fig.savefig("connection_diagram.png", dpi=100, bbox_inches="tight")
