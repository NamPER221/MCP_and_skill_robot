---
name: kicad-hardware-design
description: >-
  Rigorous hardware schematic and PCB design verification skill for KiCad,
  specialized in 24V/48V 3-phase BLDC motor controllers, gate drivers, MOSFET bridges,
  current sensing, STM32 MCU integration, CAN/RS485 transceivers, and power electronics protection.
---

# KiCad Hardware & BLDC Controller Design Review Skill

Never give vague remarks like "Mạch này có vẻ đúng" ("This circuit looks fine"). You MUST systematically audit every stage of the hardware pipeline below and verify numerical ratings against formulas and datasheets.

## Mandatory 12-Stage Audit Flow

```text
1. Schematic Structure -> 2. ERC -> 3. Net Connectivity -> 4. Power Tree -> 5. Component Ratings -> 6. Gate Driver -> 7. MOSFET Stage -> 8. Bootstrap Circuit -> 9. Current Sensing -> 10. ADC Conditioning -> 11. Protection & Transceivers -> 12. PCB Layout & DRC
```

### 1. Power Tree & Voltage Ratings
- For a $24\,\text{V}$ nominal ($29.4\,\text{V}$ max charged Li-ion / regenerative braking spike) or $48\,\text{V}$ BLDC bus:
  - **MOSFET $V_{\text{DS}}$ rating**: Must have $\ge 1.5\times - 2\times$ margin over max bus voltage plus ringing (e.g., $\ge 60\,\text{V}$ MOSFETs for $24\,\text{V}$ bus; $\ge 80\,\text{V}-100\,\text{V}$ MOSFETs for $48\,\text{V}$ bus).
  - **Bulk Electrolytic + Ceramic Capacitors**: Verify voltage derating ($\ge 50\,\text{V}$ caps for $24\,\text{V}$ bus) and low-ESR MLCCs ($100\,\text{nF} + 1\,\mu\text{F} - 10\,\mu\text{F}$ X7R) placed right across each half-bridge $V_{\text{BUS}}$ to $\text{PGND}$.

### 2. Gate Driver & Bootstrap Circuit (e.g. IR2110, FD6288, DRV8301/8323, STGAP)
- **Bootstrap Diode ($D_{\text{boot}}$)**: Must be an **ultra-fast recovery ($t_{rr} < 50\,\text{ns}$) or Schottky diode** rated above $V_{\text{BUS,max}}$. Never use slow 1N4007!
- **Bootstrap Capacitor ($C_{\text{boot}}$)**:
  - Calculate total gate charge required:
    $$C_{\text{boot}} \ge \frac{10 \times Q_{g,\text{total}}}{\Delta V_{\text{boot}}}$$
  - Typically $100\,\text{nF} - 1\,\mu\text{F}$ low-ESR X7R ceramic capacitor, placed directly adjacent to `VB` and `VS` pins.
- **Gate Resistors ($R_{g,\text{on}}$, $R_{g,\text{off}}$) & Miller Effect**:
  - Verify series gate resistor ($2.2\,\Omega - 22\,\Omega$) to damp $LC$ gate ringing ($L_{\text{trace}} C_{\text{iss}}$).
  - Check fast turn-off diode in parallel with $R_g$ (asymmetric turn-on / turn-off) and Gate-to-Source pull-down resistor ($10\,\text{k}\Omega$) on every MOSFET so gates never float when MCU is in reset.
- **Dead-Time Verification**:
  - Ensure hardware or MCU timer dead-time ($t_{\text{dead}} > t_{d(\text{off})} + t_f - t_{d(\text{on})}$) prevents shoot-through between High-Side and Low-Side MOSFETs.

### 3. Current Sensing & ADC Front-End
- **Shunt Resistor ($R_{\text{shunt}}$)**:
  - Check power dissipation at peak and continuous RMS current:
    $$P_{\text{shunt}} = I_{\text{RMS}}^2 \times R_{\text{shunt}}$$
    Ensure at least $2\times$ power derating (e.g. $1\,\text{m}\Omega - 5\,\text{m}\Omega$, $2\,\text{W} - 5\,\text{W}$ Kelvin 4-terminal footprint).
- **Current Sense Amplifier (Op-Amp / INA240 / Internal PGA)**:
  - **Kelvin Connection**: Differential sense traces (`SHUNT+`, `SHUNT-`) MUST tap directly from the inner pads of the shunt resistor, routed as a tight differential pair away from high $dI/dt$ copper pours.
  - Check **Common-Mode Voltage Range ($V_{\text{CM}}$)** (especially critical if doing in-line phase sensing or high-side sensing vs low-side shunt sensing).
  - Verify $1.65\,\text{V}$ ($V_{\text{REF}}/2$) bidirectional offset bias and RC anti-aliasing filter ($f_c = \frac{1}{2\pi R C}$) before the STM32 ADC input pin, synchronized with PWM center-aligned trigger (`TIM1_TRGO`).

### 4. Protection & Communication Isolation
- **TVS Diode** on DC bus input to clamp inductive voltage spikes during Emergency Stop or regeneration.
- **Overcurrent Hardware Comparator** wired to STM32 `TIM1_BKIN` (Break Input) for sub-microsecond hardware PWM shutoff without software latency.
- **CAN / RS485 Transceivers**: Verify ESD protection TVS on `CAN_H`/`CAN_L` and `A`/`B`, optional $120\,\Omega$ termination jumper, and common-mode choke/isolation if routing off-board.

### 5. PCB Layout & Ground Partitioning (DRC)
- **Minimize High-$dI/dt$ Switching Loop Area**: Decoupling MLCC + High-Side FET + Low-Side FET + Shunt must form the tightest possible loop.
- **Gate Drive Loop**: Route Gate trace and Source return (`VS`/`PGND`) directly parallel or stacked to minimize parasitic gate inductance.
- **Ground Return Strategy**: Separate noisy Power Ground (`PGND` carrying 20–100A motor switching currents) from sensitive Analog/MCU Ground (`AGND`/`GND`), joining at a single Star Point near the control power supply / shunt reference so motor current NEVER flows underneath the STM32 or Op-Amp!
