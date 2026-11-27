# KH2FM PS2 to Steam save converter

Bring a Kingdom Hearts II Final Mix campaign from PCSX2 into a Steam Load Game slot. You need Python 3.9+ and an in-game save in each version.

1. Close both games and let Steam Cloud finish syncing.
2. In PCSX2, open **Settings → Memory Cards** and find the card you saved on. It’s usually `Documents\PCSX2\memcards\Mcd001.ps2`. For a folder card, use the folder containing the individual save directories.
3. Find your own `KHIIFM_WW.png` under `Documents\My Games\KINGDOM HEARTS HD 1.5+2.5 ReMIX\Steam\<your Steam ID>\`.
4. Drag the card onto `list-saves.bat` or run the first command below. Pick your PS2 slot by location, level and play time. The second command imports PS2 slot 1 into Steam slot 2. Change the paths and numbers to yours.

```bat
py -3 kh2save.py list "C:\cards\Mcd001.ps2"
py -3 kh2save.py convert "C:\cards\Mcd001.ps2" --source 1 --into "C:\saves\KHIIFM_WW.png" --slot 2
```

Open **Load Game** and choose slot 2. On Linux or macOS use `python3` in place of `py -3`.

- **Slots.** Choose a Steam slot from 1 to 99. Replacing an occupied slot takes `--replace`. The system file stays with your Steam account. To write a separate file, add `--out imported.png`.
- **Undo.** Close the game and copy the timestamped `.bak` beside your Steam save back over `KHIIFM_WW.png`.
- **Cards.** Use an 8, 16, 32 or 64 MiB PCSX2 image or a folder card. JP Final Mix and US-edition Final Mix folders are recognized. If both have the same slot number, give `--source` the full folder name from `list`. Original US/EU KH2 saves and emulator save states use different formats.
- **Mods.** Use the matching PC mod. Difficulty names in the list are vanilla. For the level-25 Underworld Entrance checkpoint from the original mod’s V0.20 release, `--nmc-rmc` migrates room flags and Drive Form rewards for RMC.
- **Verification.** Run `python3 -m unittest -v`. The tests cover generated memory cards, slot selection and byte preservation outside the imported slot.

## more kingdom hearts stuff

- [Roxas May Cry](https://github.com/dexedrne/roxas-may-cry): the Roxas campaign played to the end, built on your PC from your own game files
- [NMC Fixed](https://github.com/dexedrne/NMC-Fixed): the original mod with every fix and addition, for the Steam version through OpenKH
- [KH2 native port](https://github.com/dexedrne/nmc-recomp): the game and the mod recompiled to run natively on iPhone, macOS and Linux
- [nmc-decomposed](https://github.com/dexedrne/nmc-decomposed): the mod as readable patches, rebuilt from your own copy of the game
- [358/2 Days on iPhone](https://github.com/dexedrne/khdays-port/tree/ios) — single screen on iPhone and iPad, DualSense and Switch Pro controllers, touch controls, HD cutscenes, 60 to 120 fps
