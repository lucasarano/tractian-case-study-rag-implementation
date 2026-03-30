TRACTIAN — Historical Incident Reports  
Plant: North  
Asset: GEN-KD27-003 / Kohler KD27V12  
Period: 2025

===

INCIDENT #INC-2025-0019  
date: 2025-02-03  
severity: HIGH  
asset: GEN-KD27-003

## summary
generator shutdown during scheduled weekly load test at 14:30. Black exhaust smoke observed ~10 seconds prior to ECU auto-shutdown. facility temporarily on utility power (no outage to production).

## ECU fault codes
- SPN 94 / FMI 1 — fuel supply critical underpressure

## root cause  
water contamination in fuel supply. Water separator on primary fuel filter found with ~200mL accumulated water. Main fuel filter severely clogged with dark residue. Further investigation found cracked fuel tank vent cap allowing moisture ingress.

## corrective actions
1. drained water separator
2. replaced main fuel filter (Kohler TP-11027)  
3. bled fuel system per OEM procedure sec 5.7
4. replaced cracked fuel tank vent cap
5. ordered additional spare fuel filters for site inventory

## downtime: 3.5 hours
## cost: ~$450 (parts + labor)

## recommendations
- add fuel tank vent inspection to monthly SL0 checklist
- consider fuel polishing system for bulk storage tank

===

INCIDENT #INC-2025-0087  
date: 2025-04-25  
severity: MEDIUM  
asset: GEN-KD27-003

## summary
coolant high temperature alarm (103°C, limit 105°C) triggered on SCADA during morning loaded run. generator was manually shut down within 5 minutes of alarm.

## investigation
- coolant level found ~4L below minimum
- no visible external leaks on hoses or radiator
- pressure test of cooling system revealed pinhole leak in coolant pipe at thermostat housing
- pipe corrosion noted — adjacent fasteners also showing early corrosion

## corrective actions
1. replaced coolant pipe section + thermostat gasket
2. refilled cooling system (+8L Kohler 50/50 pre-mixed coolant)
3. flagged thermostat housing area for enhanced visual inspection
4. applied anti-corrosion treatment to surrounding fasteners

## downtime: 4.5 hours (includes 2hr wait for parts from warehouse)
## cost: ~$320

## recommendations  
- stock critical cooling system gaskets/pipes on-site
- add thermostat housing corrosion check to SL0 visual inspection

===

INCIDENT #INC-2025-0134  
date: 2025-07-17 thru 2025-08-14  
severity: MEDIUM  
asset: GEN-KD27-003

## summary
intermittent metallic knock/whine reported during startup and under >75% load. Initially suspected turbocharger (V-band clamp found loose), but knock persisted after clamp fix.

## investigation timeline
- Jul 17: loose compressor inlet V-band clamp tightened, resolved whistling noise  
- Jul 22: knock reproduced under 75% load, localized to cylinder bank B  
- Aug 14: bore scope inspection (with Kohler field service)
  - cyl 8: slight liner scoring (within wear limits)
  - cyl 10: injector tip partially coked, asymmetric spray pattern → root cause of knock

## corrective actions
1. replaced cyl 10 injector (Kohler INJ-KD27-012R)
2. ran fuel additive treatment for 50hrs post-repair
3. post-repair load test — no knock at any load point

## downtime: 8 hours (bore scope + injector replacement)
## cost: $3,200 (injector $2,400 + field service $800)

## recommendations
- fuel sample testing quarterly to catch deposit formation early
- consider fuel additive program for ongoing injector health

===

INCIDENT #INC-2025-0156  
date: 2025-09-05  
severity: LOW  
asset: GEN-KD27-003

## summary
ECU alarm for DEF quality sensor out of range during routine run.

## ECU fault codes
- SPN 4334 / FMI 18 — DEF quality sensor reading out of range

## root cause
DEF fluid in tank appeared discolored/degraded. Suspected improper storage by supplier (heat exposure during summer months).

## corrective actions  
1. drained & cleaned entire DEF tank + supply lines (~40L)
2. refilled with verified fresh DEF (ISO 22241)
3. replaced DEF filter (SL1-5320)
4. cleared ECU fault code — did not return
5. notified procurement team re: supplier storage practices

## downtime: 2 hours
## cost: ~$280

===

INCIDENT #INC-2025-0171  
date: 2025-09-28  
severity: HIGH  
asset: GEN-KD27-003

## summary
low oil pressure warning during loaded operation — 2.0 bar (minimum spec 2.5 bar). generator runtime at 1,241 hours. load reduced immediately, then generator shut down for investigation.

## investigation
- oil level OK (slightly above midpoint on dipstick)
- oil appeared visually thin  
- rush oil sample sent to lab
- Lab result (Sep 30): **fuel dilution at 4.7%** (threshold 3%), TBN 5.2 (still acceptable)
- cyl 10 injector (replaced Aug) — seating fine, no leakback
- ECU injector quantity test found **cyl 3 injector leaking past return** — fuel dribble leak washing into crankcase

## corrective actions
1. replaced cyl 3 injector
2. full oil drain + refill (101L)
3. replaced both oil filters
4. post-repair oil pressure: 4.0 bar at full load — nominal
5. follow-up oil sample at +100hrs to confirm no recurrence

## downtime: 2 days (waiting for lab results before restart)
## cost: ~$3,800 (injector + oil + filters + expedited lab analysis)

## recommendations
- implement quarterly injector return-quantity checks via ECU diagnostics
- oil sample interval reduced from 500hrs to 250hrs for remainder of year
- consider fuel quality improvements (polishing system) to reduce injector stress
