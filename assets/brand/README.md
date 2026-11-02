# Kayé brand assets

**Symbol**: a money cowrie, the historic currency of West Africa. Its aperture is drawn as a zigzag
of teeth, which also reads as a voice wave: Kayé listens, then writes it down.

| File | Use |
| --- | --- |
| `symbol-{night,cauri,solaire}.svg` | Symbol alone, transparent aperture |
| `wordmark-night.svg`, `wordmark-cauri.svg` | Wordmark "kayé" (Bricolage Grotesque 700, outlined) |
| `lockup-night.svg`, `lockup-cauri.svg` | Symbol + wordmark: the cowrie spans the word's ink, from the top of the « k » to the bottom of the « y » |
| `profile-*-640.png`, `profile-*-2048.png` | Profile picture for WhatsApp, Facebook, Instagram (cropped to a circle) |
| `pattern-kente.svg` | Pattern inspired by Ewe kente strip weaving, built from brand shapes |
| `icons/*.svg` | Icon set cut like adinkra stamps: organic filled shapes on a 64 px grid, Nuit, punctuated by Solaire dots (coins, seeds, cowries). Cuts are drawn in Cauri, so use them on a Cauri background |

**Colours**: Nuit de Lomé `#14111B`, Cauri `#F5E9D6`, Solaire `#FF7A1F`, Latérite `#B84A1E`
(amounts still due), Lagune `#17705F` (paid).

Lockups, profile pictures and the README images are generated: `uv run python -m scripts.brand_export`.

**Type**: Bricolage Grotesque for titles and amounts, Inter for text. The wordmark outlines are
derived from Bricolage Grotesque (SIL Open Font License 1.1).
