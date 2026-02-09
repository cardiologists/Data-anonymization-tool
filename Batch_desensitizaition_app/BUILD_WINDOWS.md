# Windows打包说明

## 环境准备

1. 安装Python 3.8+（64位）
2. 安装必要的包：
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   pip install py2exe  # 或 cx_Freeze
3. 由icon.png生成windows图标格式.ico

## 使用PyInstaller打包

1. 单文件可执行程序
   ```bash
   pyinstaller --onefile --windowed ^
      --icon=assets/app_icon.ico^
      --name="MedicalDataAnonymizer"^
      app_update.py
2. 带依赖文件夹的打包
   ```bash
   pyinstaller --windowed^
      --icon=assets/app_icon.ico^
      --name="MedicalDataAnonymizer"^
      --add-data "assets;assets"^
      app_update.py
3. 详细配置打包
   ```batch
    pyinstaller --onefile --windowed ^
      --icon=assets/app_icon.ico ^
      --name="MedicalDataAnonymizer" ^
      --add-data "assets;assets" ^
      --hidden-import cv2 ^
      --hidden-import pydicom ^
      --hidden-import PIL ^
      --hidden-import numpy ^
      --clean ^
      app_update.py

## 测试打包结果

在Windows上直接运行.exe文件
测试各功能模块
确保不需要额外安装Python环境
