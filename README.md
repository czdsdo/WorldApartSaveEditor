# 不问凡尘存档修改器

适用于 Windows 的《不问凡尘》存档编辑器。支持修改角色属性、修为、天赋点和背包数量，以及搜索字段、备份和恢复存档。

启动时窗口自动最大化，可以通过标题栏还原。预编译版本可在 [GitHub Releases](https://github.com/czdsdo/WorldApartSaveEditor/releases) 下载。

使用 Python 3.14，在项目目录运行以下命令。

```powershell
python -m pip install -r requirements.txt
python editor.py
```

如果需要独立 EXE，可用 PyInstaller 打包。

```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --windowed --name WorldApartSaveEditor editor.py
```

生成的 EXE 位于 `dist` 目录。存档操作见[使用说明](使用说明.md)。本地存档、备份和构建产物由 `.gitignore` 排除。

`test_editor.py` 和 `test_ui.py` 使用本机已有的游戏存档作为测试输入。
