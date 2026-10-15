# -*- coding: utf-8 -*-
"""Render all mathematical equations as crisp, publication-grade LaTeX images at 300 DPI.
Output directory: results/equations/
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EQ_DIR = os.path.join(ROOT, "results", "equations")
os.makedirs(EQ_DIR, exist_ok=True)

eqs = [
    (1, r's_t = \left\langle \bar{W}_t, \; \sigma_B, \; N_q, \; \frac{\delta}{\bar{W}_t}, \; \rho_{\mathrm{preempt}}, \; q_{t-1} \right\rangle'),
    (2, r'Q^*(s_t, a_t) = \mathbb{E}\left[ R_t + \gamma \max_{a^\prime \in \mathcal{A}} Q^*(s_{t+1}, a^\prime) \;\middle|\; s_t, a_t \right]'),
    (3, r'R(t) = R_{\mathrm{comp}} + R_{\mathrm{switch}} + R_{\mathrm{wait}} + R_{\mathrm{convoy}}'),
    (4, r'R_{\mathrm{switch}} = -\beta \cdot \left(\frac{\delta}{\bar{W}_t}\right)'),
    (5, r'R_{\mathrm{convoy}} = -\eta \cdot \max\left(0, \; q_t - \hat{B}_{\mathrm{short}}\right)'),
    (6, r'\mathrm{Age}(p_i) = t_{\mathrm{now}} - t_{\mathrm{arrival}}(p_i) \leq \tau_{\mathrm{starve}}'),
    (7, r'\mathrm{Composite} = \mathrm{AWT} + \mathrm{ATT} + \frac{\delta \cdot \mathrm{CS}}{N_{\mathrm{cores}}}'),
    (8, r'\sum_{i=1}^N B_i = \int_0^{T_{\mathrm{makespan}}} \sum_{c=1}^{N_{\mathrm{cores}}} \mathbb{I}(\mathrm{Core}_c \text{ is busy}) \, dt')
]

for idx, latex in eqs:
    fig, ax = plt.subplots(figsize=(8, 1.0), dpi=300)
    ax.axis("off")
    # Use Computer Modern math style
    ax.text(0.5, 0.5, f"${latex}$", fontsize=15.0, ha="center", va="center",
            transform=ax.transAxes, color="#0F172A")
    out = os.path.join(EQ_DIR, f"eq_{idx}.png")
    fig.savefig(out, bbox_inches="tight", pad_inches=0.04, transparent=True, dpi=300)
    plt.close(fig)
    
    im = Image.open(out)
    print(f"Rendered eq_{idx}: size={im.size}, aspect={im.size[0]/im.size[1]:.2f} -> {out}")
