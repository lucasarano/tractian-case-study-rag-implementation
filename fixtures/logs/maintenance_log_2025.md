# Plant North — Generator Maintenance & Incident Logs 2025

---

## jan 15 2025 — routine check SL0

tech: R. Mendes  
machine: GEN-KD27-003 (kohler gen backup north)

oil level ok, between min/max on dipstick  
coolant level good — topped off maybe 0.5L  
fuel prefilter water separator — drained, no significant water  
visual inspection, no leaks  
belt tension looks fine, no cracking on v-ribbed belt  
BATTERY voltage 27.1V, connections clean

everything nominal. next scheduled SL1 at 500hrs or 6mo

---

## FEB-03-2025 — UNPLANNED SHUTDOWN 

**machine: GEN-KD27-003**  
tech: R. Mendes + A. Costa

Generator tripped during weekly load test around 14:30. Black smoke observed from exhaust for ~10 seconds before auto-shutdown. ECU showed SPN 94 FMI 1 (fuel supply critical underpressure).

Checked fuel level — tank at 60%.  
Opened primary fuel filter/water separator — found significant water accumulation, maybe 200mL.  
DRAINED water separator completely.  
Main fuel filter — clogged bad. Dark residue on filter element. Replaced with new Kohler OEM filter (P/N TP-11027).  
Bled fuel system per manual sec 5.7.  
Restarted — ran smooth, no smoke.  

Root cause: water ingress in fuel tank vent cap was cracked. replaced vent cap.

NOTE: ordered 3x spare main fuel filters to keep on-site

---

## 2025-02-21, ~08:00

tech: D. Oliveira  
GEN-KD27-003 — OIL CHANGE (SL1-2020)

runtime hrs: 487  
oil drained hot, good flow from drain valve  
old oil was dark but not sludgy, sent sample to lab  
filled 101L Mobil Delvac 1300 Super 15W-40  
replaced 2x oil filters (P/N LP-4089) — hand tight + 1/2 turn per manual  
reset service interval counter  
also replaced crankcase breather separator filter (SL1-1661) while we were at it — old one was starting to show oil mist

---

##  mar 12 — load bank test

tech: R Mendes

full load test 2hrs on GEN-KD27-003. all params nominal:

| Parameter | Value | Spec |
|-----------|-------|------|
| coolant temp | 82°C | <105°C |
| oil pressure | 4.2 bar | 2.5-6.0 bar |  
| oil temp | 98°C | <120°C |
| charge air press | 2.1 bar | >1.8 bar |
| exhaust temp | 540°C | <600°C |
| fuel consumption | 68 L/hr | ~65-72 L/hr |
| battery charge alt | 28.3V | 27-29V |

no anomalies. smoke test clean

---

## 25-APR-2025 generator alarm COOLANT TEMP HIGH

tech: A. Costa  
GEN-KD27-003  
09:45 — got alarm on SCADA, coolant temp spiked to 103°C during morning run  

checked coolant level — LOW, about 4L below min!!  
no visible external leaks on hoses or radiator  
shut down and let cool  
pressure tested cooling system — found pinhole leak on coolant pipe at thermostat housing, barely visible  
replaced coolant pipe section + new thermostat gasket  
refilled coolant (Kohler genuine pre-mixed 50/50, 8L added)  
restarted — temp holding steady at 83°C under load

turnaround: 4.5 hrs to get part from warehouse

> NOTE: thermostat housing area should be on the visual inspection checklist — corrosion starting on adjacent fasteners. flagged for next SL1

---

## 2025-05-30 — SL1 Full Service

GEN-KD27-003 / tech team: Mendes, Costa, Oliveira  
runtime: 973 hrs

### completed:
- oil change (SL1-2020) — 101L Shell Rimula R4 X 15W-40 + 2 filters
- coolant analysis (SL1-3021) — sample sent, pH 8.1, no contamination
- fuel prefilter replaced (SL1-4110) 
- main fuel filter replaced (SL1-4120)
- valve clearance checked (SL1-1122) — ALL IN SPEC (intake 0.40mm, exhaust 0.60mm)
- belt drive inspection (SL1-3281) — coolant pump belt replaced, showing glazing. battery alt belt OK
- fan drive belt (SL1-7221) — slight fraying on edge, replaced as precaution
- exhaust aftertreatment check (SL0-5301) — DEF level adequate, no DTC codes
- visual inspection complete — noted minor oil weep at rear main seal area, monitoring

### parts used:
| Part | Qty | P/N |
|------|-----|-----|
| oil filter | 2 | LP-4089 |
| fuel prefilter | 1 | FP-2241 |
| main fuel filter | 1 | TP-11027 |
| coolant pump belt | 1 | BT-3281-A |
| fan drive belt | 1 | BT-7221-C |
| engine oil 15W-40 | 101L | — |
| coolant sample kit | 1 | — |

---

## Jul-17 2025 — weird noise on startup

tech: R. Mendes

GEN-KD27-003 started making a metallic whistling/whining noise right after startup, goes away after ~30sec when warm. Only at idle, not under load.

checked turbocharger — inlet hose clamp was loose on compressor side. tightened V-band clamp to spec.  
Noise gone after fix.  

~~also hearing a faint knock under load but couldn't reproduce consistently. will monitor~~

Update jul-22: knock reproduced under 75% load. sounds like its coming from cylinder bank B. Pulled ECU log — no fault codes stored. Oil analysis from may came back clean.  
**Scheduling bore scope inspection for next window.**

---

## 2025-08-14 bore scope + investigation

tech team: D. Oliveira + Kohler field service (J. Patterson)

bore scope on GEN-KD27-003 cyl bank B:
- cyl 7: normal carbon pattern, injector spray pattern ok
- cyl 8: SLIGHT scoring on liner wall, not deep. within wear limits per Kohler
- cyl 9: normal
- cyl 10: injector tip showing asymmetric spray — one hole partially coked. causing the intermittent knock
- cyl 11: normal  
- cyl 12: normal

**Action: replaced cyl 10 injector** (Kohler P/N INJ-KD27-012R). Rechecked — knock gone at all load points.

Kohler rep recommended: run fuel additive treatment next 50hrs, then pull another fuel sample to check for injector deposit trend.

cost: $2,400 (injector) + $800 (field service call)

---

## sept 5 — DEF system fault

machine: GEN-KD27-003  
tech: A Costa

ECU alarm: SPN 4334 FMI 18 — DEF quality sensor reading out of range  
checked DEF tank — fluid looked discolored, possibly contaminated or degraded (exposed to heat?)

DRAINED entire DEF tank (~40L)  
cleaned tank + lines  
refilled with fresh DEF (ISO 22241)  
replaced DEF filter (SL1-5320)  
cleared ECU fault — did NOT return

suspect: DEF delivered in last batch may have been stored improperly by supplier. notified procurement.

---

## 2025-09-28 — oil pressure alarm

GEN-KD27-003  
tech: R Mendes

Low oil pressure warning at 2.0 bar during loaded run (spec min is 2.5 bar). Runtime: 1,241 hrs.

immediate actions:
1. reduced load to 50%
2. checked oil level — ok, slightly above midpoint
3. oil looked thin, possible fuel dilution???
4. shut down for investigation

oil sample taken — lab rush results pending  
**DO NOT RESTART until lab results back**

Update 09-30: lab results — fuel dilution at 4.7% (threshold is 3%). TBN still acceptable at 5.2.  
Cause investigation: cyl 10 injector (the new one from Aug) checked — seating fine, no leak. Running ECU injector quantity test... found cyl 3 injector leaking past return. Dribble leak causing fuel wash into oil.

replaced cyl 3 injector. full oil & filter change.  
Oil pressure back to 4.0 bar at full load.

---

## oct 2025 — general notes

- generator runtime as of oct-01: 1,289 hrs
- rear main seal weep getting slightly worse, small drip forming. scheduled seal replacement for Nov SL2 window
- ordered kohler seal kit P/N SK-KD27-RMS
- fuel tank vent cap (replaced in Feb) holding up fine
- thermostat housing fasteners treated with anti-corrosion compound during Sept shutdown

---

## NOV-15-2025 SL2 Major Service

GEN-KD27-003  
runtime: 1,410 hrs  
tech team: full crew + Kohler mobile service

### work performed:
1. everything from SL1 scope (oil, filters, belts, etc)
2. **rear main seal replacement** — old seal was hard and cracked, definite source of weep
3. valve clearance adjustment — cyl 5 exhaust was at 0.65mm (spec 0.60mm ±0.05), adjusted
4. crankcase breather V-ribbed belt replaced (SL1-1662)  
5. turbocharger inspected — compressor wheel in good shape, no rub marks, shaft play within spec
6. all belt tensioners checked/replaced where needed
7. cooling system flushed and refilled (55L Kohler pre-mixed coolant)
8. battery load test — 27.8V under load, CCA within spec
9. fuel injection system pressure test — all within spec after the two injector replacements earlier this year
10. ECU software checked — running v21.16.30, current per Kohler

### outstanding:
- turbo wastegate actuator showing slight hesitation at low boost. not causing issues yet but monitor at next SL1
- recommend adding fuel polishing system to tank — we've had 2 fuel quality incidents this year

total downtime: 3 days  
cost: ~$12,500 (parts + Kohler service)

---

## dec 20 2025 — cold weather prep

tech: R mendes

GEN-KD27-003 winter readiness check:
- block heater operational, cycling correctly (verified w/ thermal camera)
- battery charger/maintainer connected, float at 27.4V  
- fuel tank treated with anti-gel additive (diesel fuel quality is ASTM D975 2D-S15)
- DEF tank heater verified operational (DEF crystallizes below -11°C)
- coolant tested — freeze protection to -37°C, good for our climate
- all drain points accessible and marked
- emergency start procedure posted in control room

ready for winter ops 👍
