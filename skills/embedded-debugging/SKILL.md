---
name: embedded-debugging
description: >-
  Systematic embedded MCU debugging methodology for STM32 and ESP32 firmware:
  UART, RS485/Modbus RTU, CAN/bxCAN/FDCAN, SPI, I2C, PWM, ADC, Timers, Quadrature Encoders,
  Interrupts (NVIC), DMA, and Watchdog resets.
---

# Embedded MCU Debugging Skill (STM32 / ESP32)

Use this skill when debugging firmware or hardware-software integration on STM32 (HAL/LL/CMSIS/FreeRTOS) or ESP32. Follow the evidence-based checklist below:

## 1. Clock Tree & Reset Cause
- Verify `HSE_VALUE` in firmware matches the physical crystal on the PCB (e.g., 8 MHz vs 25 MHz on STM32F4/F1/G4/H7). A mismatch scales all UART baudrates, CAN bitrates, and Timer frequencies!
- Inspect MCU reset flags (`RCC->CSR` on STM32: `IWDGRSTF`, `WWDGRSTF`, `BORRSTF`, `PINRSTF`, `LPWRRSTF`) to detect brown-out or watchdog resets during motor startup.

## 2. Peripheral-Specific Checklists

### UART / RS485 / Modbus RTU
- Verify Baudrate, Word Length (Attention: on STM32, enabling Parity bit requires `UART_WORDLENGTH_9B` for 8-bit data + 1 parity bit!), Stop bits.
- For RS485 half-duplex transceivers (MAX485, SP3485):
  - Check `DE`/`RE` direction pin timing: do NOT de-assert `DE` when `TXE` (TX Empty) fires; wait until **`TC` (Transmission Complete)** flag is set, otherwise the last byte/CRC is truncated!

### STM32 bxCAN / FDCAN
- Verify APB1 clock frequency (`PCLK1`) and bit timing:
  $$\text{Bitrate} = \frac{f_{\text{PCLK1}}}{\text{Prescaler} \times (1 + \text{BS1} + \text{BS2})}$$
- **Classic STM32 bxCAN Pitfall**: Have you configured and enabled at least one **CAN Filter Bank** (`HAL_CAN_ConfigFilter`) before calling `HAL_CAN_Start`? Without an enabled filter bank, RX FIFO0/FIFO1 will silently drop 100% of incoming frames!
- On dual-CAN STM32 (`CAN1` + `CAN2`), `CAN2` depends on `CAN1` clock (`__HAL_RCC_CAN1_CLK_ENABLE()`) and filter bank `SlaveStartFilterBank`.

### Timer / PWM / Quadrature Encoder
- **Encoder Mode (`TIM_ENCODERMODE_TI12`)**:
  - Check counter bit-width (`16-bit` on TIM3/TIM4 vs `32-bit` on TIM2/TIM5). Handle 16-bit signed overflow (`int16_t(TIMx->CNT - prev_cnt)`) properly when computing velocity!
  - Configure input digital filter (`IC1Filter`, `IC2Filter` = `0x06..0x0F`) to reject high-frequency MOSFET switching noise.
- **Advanced Motor PWM (`TIM1` / `TIM8`)**:
  - Verify `MOE` (Main Output Enable) bit in `BDTR` (`__HAL_TIM_MOE_ENABLE`) and Dead-Time Generator (`DTG`) configuration before enabling 3-phase bridge outputs.

### Interrupts (NVIC) & DMA Concurrency
- Variables shared between ISR/DMA callbacks and main loop/RTOS tasks MUST be declared `volatile` or synchronized via RTOS queues/notifications.
- Keep ISRs short: never call blocking `HAL_Delay()` or heavy `printf` inside an ISR.
- On STM32F7/H7 with D-Cache enabled, DMA buffers must reside in non-cacheable SRAM/MPU regions or use explicit `SCB_CleanDCache_by_Addr` / `SCB_InvalidateDCache_by_Addr`.
