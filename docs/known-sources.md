# Known transmitters

`configs/known_sources.yaml` is the catalog the verdict step uses. A frequency inside a range, or within 50 kHz of a downlink centre, is `KNOWN_SOURCE`. Checked 2026-10-12.

## GPS L1

IS-GPS-200N, dated 01 August 2022, section 3.3.1.1, says the L1 nominal carrier is 1575.42 MHz. The same section says that for GPS III the requirements pertain to a 30.69 MHz band centered on that carrier. The catalog edges are 1560.075 MHz and 1590.765 MHz, which is 1575.42 ± 15.345. The PDF is on [gps.gov](https://www.gps.gov/sites/default/files/2025-07/IS-GPS-200N.pdf).

## GPS L2

The same section says the L2 nominal carrier is 1227.6 MHz, with the same 30.69 MHz GPS III band. The catalog edges are 1212.255 MHz and 1242.945 MHz.

## GLONASS L1 FDMA

The GLONASS interface control document for the L1 and L2 navigation signal, edition 5.1 (2008), section 3.3.1.1, sets the L1 reference at 1602 MHz and the channel step at 562.5 kHz. Table 3.1 lists nominal carriers from channel −7 at 1598.0625 MHz through channel +6 at 1605.375 MHz. The catalog uses those two endpoints. It does not add the modulation width. The English PDF read for this entry is the [2016 archive copy](https://web.archive.org/web/20160414062343/http://www.spacecorp.ru/upload/iblock/1c4/cgs-aaixymyt%205.1%20ENG%20v%202014.02.18w.pdf) of the Russian Space Systems document.

## Voyager 1 X-band

EXP-001 run `20261012T130904642405Z-exp-001-voyager` selected hit 2 at an uncorrected frequency of 8419.297028 MHz. The catalog stores that centre. The ±50 kHz window is this project's downlink rule. A Deep Space Network channel plan was not used, because the 8400–8450 MHz sentence was not read from the DSN handbook itself.

## Left out

Iridium, Inmarsat, GPS beyond the GPS III bandwidth above, the GLONASS L2 carrier span, and a general Mars X-band range are not in the file. No primary sentence for those edges was in hand on 2026-10-12. The EXP-004 line near 5999.99 MHz is not a transmitter. It lives only in `configs/fixtures/exp004_known_sources.yaml`.
