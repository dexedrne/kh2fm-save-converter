# KH2FM PS2 to Steam save converter

Bring one **Kingdom Hearts II Final Mix** campaign from PCSX2 into a Load Game slot on Steam. You need Python 3.9 or newer, a Japanese Final Mix memory card (SLPM-66675), and an existing Steam KH2FM save. Everything runs locally with the Python standard library.

## Windows quick start

1. Make an in-game save at a save point in each version. Close the games and wait for Steam Cloud to finish syncing. Copy your Steam save somewhere safe.
2. Find the active card in PCSX2’s **Settings → Memory Cards**. A common location is `Documents\PCSX2\memcards\Mcd001.ps2`. Portable installations often keep `memcards` beside the emulator. For a folder card, choose the directory containing the individual save folders.
3. Find `KHIIFM_WW.png` under `Documents\My Games\KINGDOM HEARTS HD 1.5+2.5 ReMIX\Steam\<your Steam ID>\`. If Documents is synced to OneDrive, look there too.
4. Drag your card onto **list-saves.bat**. The list shows the PS2 slot, folder, world/room code, level, play time and difficulty. Pick the campaign you recognize.
5. Open Command Prompt in the converter folder. Replace both paths below with yours. This example imports **PS2 slot 1** into **Steam slot 2**.

```bat
py -3 kh2save.py list "C:\cards\Mcd001.ps2"
py -3 kh2save.py convert "C:\cards\Mcd001.ps2" --source 1 --into "C:\saves\KHIIFM_WW.png" --slot 2
```

Open **Load Game** in Steam and choose slot 2. The converter reads the memory card and writes a timestamped `.bak` beside the Steam file before saving. An occupied slot requires `--replace`. To create a separate PNG, append `--out "C:\saves\imported.png"` with an unused filename. On Linux and macOS, use `python3` in place of `py -3`.

## FAQ

**How do I undo an import?** Close the game, copy the timestamped backup over `KHIIFM_WW.png`, then reopen the game. Keep the backup until you have played and saved successfully.

**Why is my card missing from the list?** Use a standard 8, 16, 32 or 64 MiB PCSX2 card image or an unpacked folder card. Emulator save states and exported save archives need an in-game memory-card save first. The original US and European KH2 releases use a different save format. On mixed cards, only JP Final Mix campaigns appear.

**What carries over?** The campaign carries its recorded progress, inventory and stats. The Steam system file and other slots are preserved. PC-only content such as Holo-Archive history has no equivalent PS2 record.

**What about mods?** Use a matching PC version of the mod. Mods can rename rooms and difficulty levels or interpret story flags differently. The list uses vanilla difficulty names alongside their numeric values. By default, the converter carries the campaign bytes across directly. The optional `--nmc-rmc` applies a known room, story-flag and Drive Form migration for one specific level-25 Underworld Entrance checkpoint from Nobody May Cry V0.20 to RMC. Other checkpoints are refused with that option.

**Can I use someone else’s Steam PNG?** Use your own account’s file. Steam encodes the system directory for that account. Save once in the PC game to initialize it.

## more kingdom hearts stuff

- [NMC Fixed](https://github.com/dexedrne/NMC-Fixed): the original mod with every fix and addition, for the Steam version through OpenKH
- [Nobody May Cry: Recompiled](https://github.com/dexedrne/nmc-recomp): the game and the mod recompiled to run natively on iPhone, macOS and Linux
- [nmc-decomposed](https://github.com/dexedrne/nmc-decomposed): the mod as readable patches, rebuilt from your own copy of the game
