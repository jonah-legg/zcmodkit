# Zero Company ModKit — Launch Plan

## Overview

Build and release the first open-source modding library for Star Wars: Zero Company.
Plant the flag as the go-to modding framework before anyone else occupies the space.

---

## The Process: From Game Install to Working Library

### Step 1: Get the Game Installed

The game releases Thursday at 11:00 AM. You're leaving work at 11:30. Start the download from your phone the moment it goes live. The game is likely 50–80 GB based on modern UE5 titles. It downloads while you pack. By the time you're done packing around 1:30 PM, the game should be installed or nearly there.

If for some reason the download didn't complete, let it finish while you set up tools and check for the AES key.

### Step 2: Get the AES Key

Every UE4/5 game that uses encrypted pak files has a 256-bit AES key baked into the binary. Without this key, you cannot read the game's archives. By 2.5 hours post-launch (when you sit down), the key may or may not be public yet. You're early. Check anyway.

Check in this order:

1. **FModel/Unreal-Game-Keys repo** — https://github.com/FModel/Unreal-Game-Keys
2. **FModel Discord** — people post keys for new releases within hours
3. **Game subreddit** — someone will share it or link a modding Discord
4. **UE4SS / RE-UE4SS Discord** — if someone got injection working, the key is a byproduct
5. **Nexus Mods page** — slower, but usually within a day

If nobody has it yet (more likely at 1:30 PM than at 5 PM — you're early), you extract it yourself:

- **Method A (Static):** Run Steamless on the game executable to strip Denuvo/DRM. Then run aes-finder against the stripped binary. It scans for 256-bit keys in the binary's data sections and prints candidates. Test each one in FModel until one decrypts.
- **Method B (Runtime):** Attach x64dbg to the running game. Set a breakpoint on `FAES::DecryptData` (find it by searching for the string or known patterns). When it hits, the key is passed as an argument in a register (typically RCX or RDX). Copy the 32 bytes out.
- **Method C (UE4SS):** If UE4SS injection works on this build, it sometimes logs the encryption key in its output console on startup.

If you find it yourself, post it publicly. This builds credibility and gets your name in front of the modding community before you even announce the library. Being the person who posts the key 2–3 hours after launch is a power move.

### Step 3: Open the Game in FModel

FModel is a visual asset browser for Unreal Engine games. Point it at the game's install directory (specifically the `Paks` folder, usually at something like `ZeroCompany/Content/Paks/`). Enter the AES key. FModel decrypts the archives and shows you the full asset tree.

What you're looking for:

- **DataTables** — These are the core data-driven tables that define game stats. They'll be somewhere like `Content/Data/` or `Content/GameData/`. Names will look like `DT_OperativeBaseStats`, `DT_WeaponData`, `DT_AbilityStats`, `DT_UpgradeTree`.
- **Blueprints** — The game logic objects. These tell you how abilities, AI, and systems are wired up.
- **The overall folder structure** — Document what you find. This becomes `docs/game-structure.md`.

Export a few DataTables as JSON from FModel. Open them. Understand the row structure — column names, data types, how operatives are keyed. This is what your library will parse and modify.

### Step 4: Run UE4SS for the SDK Dump

UE4SS is an injection framework. You drop its DLL into the game's Binaries/Win64 folder and it hooks into the running Unreal Engine process. On launch, it can dump the full SDK — every UClass, UStruct, UEnum, UFunction, and UProperty in the game's runtime.

This gives you:

- The complete class hierarchy (what inherits from what)
- Every property name and type on every class
- Every function signature
- The actual runtime names for things you saw in FModel

The dump is a collection of header files or text files. You commit these to `sdk_dump/` in your repo. They're reference material for you and for anyone else building mods later.

If UE4SS injection fails (Denuvo can interfere), this isn't a blocker. You can still build the DataTable modding library without it. The SDK dump makes the library smarter, but the core functionality — read table, change value, repack — works purely from pak file manipulation.

### Step 5: Write the Core Library

This is the real work. You're writing Python that does the following pipeline:

**Read:** Open a .pak file → decrypt with AES key → locate a specific .uasset/.uexp pair → parse the binary format → extract the DataTable rows into a Python dictionary.

**Modify:** The user changes values in the dictionary. `stats["Fixer"]["MaxHP"] = 200`.

**Write:** Serialize the modified dictionary back into valid .uasset/.uexp binary → pack it into a new .pak file with the `_P` suffix (which tells Unreal to load it as a patch, overriding the original).

The tricky parts:

- **Pak format** — Well-documented. CUE4Parse and UnrealPak handle this. You can either wrap an existing tool or implement the subset you need.
- **uasset/uexp parsing** — The binary serialization format for Unreal assets. DataTables are relatively simple: a header with column definitions, then rows of typed values. More complex assets (Blueprints, materials) are significantly harder, but you don't need those for v1.
- **Repacking** — The `_P.pak` patching system means you only need to produce a valid pak containing your modified files. The game loads patch paks last and they override originals.

What you might actually do in practice for v1: use `UnrealPak.exe` (shipped with any UE install or available standalone) to do the actual packing, and focus your Python code on the DataTable parsing and modification logic. Ship the full pipeline, even if part of it is calling an external tool under the hood.

### Step 6: Test End-to-End

Modify one value. Something obvious and instantly verifiable: an operative's max HP, a weapon's damage, an ability's cooldown. Repack it. Drop the `_P.pak` into the game's Paks folder. Launch the game. Confirm the value changed.

If it works, you have a working modding library. If it doesn't, debug — the most common issues are:

- Serialization mismatch (you wrote the binary slightly wrong, corrupting the asset)
- Pak structure issue (the game isn't loading your patch pak)
- Asset versioning (the engine detects a version mismatch and rejects the file)

Once one value roundtrips successfully, the entire DataTable system is cracked. Every stat in every table is now moddable through your library.

### Step 7: Package and Push

Clean up the code. Write the README with the real quick-start example showing real paths from the actual game. Push to GitHub. The repo should work — someone should be able to clone it, point it at their game install, and modify a stat.

---

## Schedule

### Pre-Thursday (Prep)

- Download and install all tools: FModel, UE4SS, CUE4Parse, x64dbg, Steamless, aes-finder, Python + dependencies
- Have everything in a portable folder or on the machine you're taking to college
- Join FModel Discord
- Set up the GitHub repo skeleton (README, ROADMAP, CONTRIBUTING, Discord link, empty `core/` with `__init__.py`)
- Create the Discord server for the modkit community

### Thursday, 11:00 AM — Game Releases

You're still at work for another 30 minutes. Start the download from your phone immediately.

### Thursday, 11:30 AM — Leave Work

Head home. The game is downloading in the background.

### Thursday, 11:30 AM – 1:30 PM — Pack for College

You're packing your room. Game is downloading. This is dead time for the project but necessary. Use any spare moments to check your phone for AES key posts in the FModel Discord.

### Thursday, 1:30 PM — Sit Down (Session 1: 10.5 Hours)

The game has been out for 2.5 hours. You're early. The AES key might not be public yet — you might be the one to find it.

| Time | Task |
|------|------|
| 1:30–2:00 PM | Check for AES key. If it's posted, grab it. If not, start extraction yourself. |
| 2:00–2:30 PM | Open FModel, enter key, browse the asset tree. Take screenshots. |
| 2:30–3:30 PM | Map the file structure. Find DataTables. Export a few to JSON. Document paths. |
| 3:30–4:00 PM | Attempt UE4SS injection. If it works, run SDK dump. If not, move on. |
| 4:00–7:00 PM | Write core library: pak reading, DataTable parsing, JSON export/import. |
| 7:00–7:30 PM | Break. Eat something. |
| 7:30–9:30 PM | Write repacking logic. Produce a `_P.pak` with one modified stat. |
| 9:30–10:30 PM | Test in-game. Launch, verify the modified value loaded. Debug if needed. |
| 10:30–11:30 PM | Write the working example. Clean up code. Polish what you have. |
| 11:30 PM–12:00 AM | Push everything to GitHub. Post Thursday teaser on Reddit. |

**Hard stop at midnight. You're moving into college in the morning.**

### Friday Morning — College Move-In

Move in. Set up your room. Plug in your PC. Connect ethernet. Situated no later than 12:00 PM.

### Friday, 12:00 PM — Dorm Room (Session 2: Full Afternoon + Evening)

| Time | Task |
|------|------|
| 12:00–12:30 PM | Pull repo. Re-orient. Review what worked Thursday and what didn't. |
| 12:30–1:30 PM | Fix any bugs from Thursday's session. Get the end-to-end pipeline clean. |
| 1:30–4:00 PM | Write the polished example (`change_operative_hp.py`). Write `dump_tables.py` tool. |
| 4:00–5:00 PM | Final end-to-end test: run the example, produce a mod, load it in-game, screenshot the result. |
| 5:00–6:00 PM | Break. Eat. Explore campus. You've earned it. |
| 6:00–8:00 PM | Write the real README with actual game paths, real output, real examples. Flesh out `docs/game-structure.md`. |
| 8:00–9:00 PM | Finalize ROADMAP.md with honest status of what works and what's next. |
| 9:00–10:00 PM | Final push to GitHub. Review the repo as if you're a stranger seeing it for the first time. |
| 10:00–11:00 PM | Draft the Saturday Reddit post. Include code snippet, screenshot, GitHub link, Discord link. |

### Saturday Morning — Post on Reddit

Post when the subreddit is waking up (9–11 AM depending on timezone). This is when traffic peaks on gaming subreddits during a new release weekend.

---

## Why the Earlier Start Changes Things

With 10.5 hours on Thursday instead of 7, you have a realistic shot at finishing the entire core library in Session 1. That means Friday becomes polish and documentation — not crunch. The schedule has breathing room now.

You're also sitting down only 2.5 hours after launch. There's a real chance you're the first person to extract the AES key. If you are, you post it publicly, and suddenly your name is already associated with Zero Company modding before you've even announced the library. The Thursday night teaser post hits different when you're the same person who posted the key that afternoon.

---

## Reddit Strategy

### Post 1: Thursday Night (Teaser / Flag Plant)

**Subreddit:** r/ZeroCompany (or whatever exists)
**Title:** "Got Zero Company's archives cracked open — modding library in progress"

Include:
- FModel screenshot showing the asset tree
- The AES key (useful to others)
- Discord link
- "Working modding library dropping this weekend"

This costs nothing and claims the space.

### Post 2: Saturday Morning (The Real One)

**Title:** "Working modding library for Zero Company — change any operative stat in 3 lines of Python"

Include:
- GitHub link
- Quick Start code snippet
- Screenshot/video of modified stat loading in-game
- Discord link
- What's on the roadmap

This is the one that blows up.

---

## Repository Structure

Philosophy: Everything works or it's not there. No empty folders. No placeholder files. No aspirational directory structures. Code lands with working examples the same day.

```
zero-company-modkit/
├── README.md
├── ROADMAP.md
├── CONTRIBUTING.md
├── core/
│   ├── pak.py                  (extraction + decryption)
│   ├── assets.py               (uasset/uexp parsing)
│   └── datatable.py            (DataTable read/write)
├── tools/
│   ├── dump_tables.py          (dump all DataTables to JSON)
│   └── find_aes_key.py         (AES key extraction utility)
├── docs/
│   └── game-structure.md       (what you've mapped so far)
├── examples/
│   └── change_operative_hp.py  (first working mod, end to end)
└── sdk_dump/
    └── (UE4SS output lives here)
```

Modules get added only when they work. Hooks folder appears when hooks exist. Upgrade tree module appears when it's functional. The repo grows with every commit being credible.

---

## Key Resources

| Tool | Purpose |
|------|---------|
| FModel | Asset browser, pak extraction, visual inspection |
| UE4SS | SDK dump, runtime hooks, Lua scripting |
| CUE4Parse | C# library for reading UE4/5 assets programmatically |
| Steamless | DRM stripping for static analysis |
| aes-finder | Automated AES key scanning of binaries |
| x64dbg | Debugger for runtime key extraction |

| Community | Link |
|-----------|------|
| FModel Discord | (join before Thursday) |
| FModel Unreal-Game-Keys | https://github.com/FModel/Unreal-Game-Keys |
| UE4SS GitHub | https://github.com/UE4SS-RE/RE-UE4SS |
| AES Key Extraction Guide | https://github.com/Cracko298/UE4-AES-Key-Extracting-Guide |

---

## Summary

| What | When |
|------|------|
| Game releases | Thursday 11:00 AM |
| Leave work, start packing | Thursday 11:30 AM |
| Sit down, start working | Thursday 1:30 PM |
| Session 1 (10.5 hours) | Thursday 1:30 PM – 12:00 AM |
| Move into college | Friday morning |
| Session 2 (full afternoon) | Friday 12:00 PM – 11:00 PM |
| Post on Reddit | Saturday morning |
| First mover advantage locked in | First weekend |
