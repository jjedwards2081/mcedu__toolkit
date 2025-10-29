# Unpacked Directory

This directory contains extracted Minecraft Education world contents.

## Purpose
- Contains extracted contents of unpacked .mcworld and .mctemplate files
- Each unpacked world gets its own subdirectory
- Used for analysis and modification of world contents

## Contents
- World data files and directories
- Language files (.lang) for text analysis
- World structure and configuration files

## Note
**This directory is ignored by Git** to prevent large files and user data from being committed to the repository.

## Directory Structure
Unpacked worlds are organized in timestamped directories:
```
YYYYMMDD_HHMMSS_world_name/
```

Example:
```
20231029_143530_MyWorld/
├── behavior_packs/
├── resource_packs/
├── db/
└── level.dat
```