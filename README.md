# Medical Data Anonymization Software

## Overview

A batch processing tool for anonymizing medical imaging data, including **MRI, CT, and ultrasound** modalities.  
The software provides configurable masking options for patient information removal while maintaining the **clinical utility** of the data.

---

## Features

### Multi-modality Support
- MRI data anonymization  
- CT data anonymization  
- Intracardiac Echo (ICE) ultrasound  
- Transthoracic Echo (TTE) ultrasound  
- DICOM ultrasound studies  

### Flexible Masking Options
- Configurable video masking (left / top / right)  
- JPEG watermark removal with adjustable regions  
- DICOM metadata anonymization  

### Batch Processing
- Process entire directories recursively  
- Option to keep original files (creates `*_anon` directory)  
- Progress tracking and logging  

### User Interface
- Preview capabilities for ultrasound videos and JPEG images  
- Real-time progress monitoring  
- Modality-specific configuration  

---

## System Requirements

- **Operating System:** Windows, macOS, or Linux  
- **Python:** 3.8 or higher  

### Dependencies
- OpenCV (`cv2`)  
- PyDICOM  
- Pillow (`PIL`)  
- NumPy  

---

## Installation

### From Source

Clone the repository:
```bash
git clone <repository-url>
cd medical-data-anonymizer
````

Install dependencies:

```bash
pip install -r requirements.txt
```

### Executable Version

Pre-built executables are available for **Windows** and **macOS** in the **Releases** section.

---

## Usage

### Running the Software

Launch the application:

```bash
python app_update.py
```

1. **Agree to the terms of use**

   * The software displays usage terms and developer information
   * Click **OK** to proceed

2. **Configure processing**

   * **Select Input Directory:** Choose the folder containing medical data
   * **Choose Modality:** Select the appropriate imaging modality

3. **Configure Masking (if applicable)**

   * **Ultrasound:** Set mask direction and size
   * **MRI / CT:** Configure JPEG watermark regions

4. **Options**

   * Keep original files (creates `*_anon` directory)
   * Process directly (modifies files in place)

5. **Start Processing**

   * Click **Run** to begin batch processing
   * Monitor progress in the output log
   * Use **Stop** to halt processing at any time

---

## Input Directory Structure

The software automatically detects case directories based on content:

* **MRI / CT:** Directories containing DICOM files
* **Ultrasound:** Directories containing AVI files or DICOM studies
* **JPEG images:** Found in `exam/jpeg` subdirectories or any location

---

## Modality-Specific Processing

### MRI / CT Processing

* Anonymizes DICOM metadata
* Removes patient identifiers
* Processes JPEG screenshots with configurable masking

### Ultrasound Processing

* **Video files (AVI):** Applies black masking to specified areas
* **DICOM studies:** Complete DICOM anonymization
* **Preview:** Allows visual confirmation of masking parameters

---

## Configuration

### Ultrasound Mask Settings

* **Direction:** Left, Top, or Right masking
* **Size:** Pixel width of the mask (adjustable with preview)
* **Maximum ratio:** Limited to **75%** of image dimension to preserve clinical utility

### JPEG Mask Settings

* Interactive region selection (draw rectangles over sensitive areas)
* Masking method: Black fill (other methods available in code)
* Batch application: Configure once, apply to all JPEGs

---

## Output

### File Structure

* If **Keep original** is enabled: Creates `[input]_anon` directory
* Maintains original directory structure
* Processes all supported file types

### Logging

* Real-time progress updates
* Case-by-case processing details
* Error reporting with tracebacks
* Final summary statistics

---

## Important Notes

### Data Safety

* **Backup your data before processing**
* Test on sample data before full batch processing
* The **Keep original** option is recommended for first-time use

### Clinical Considerations

* Masking preserves clinical utility while removing identifiers
* 75% maximum mask ratio ensures diagnostic regions remain visible
* DICOM anonymization follows **DICOM PS3.15** standard

### Legal Compliance

* This tool is for **internal use only**
* Users must comply with local privacy regulations (HIPAA, GDPR, etc.)
* The developer assumes no liability for data loss or misuse

---

## Troubleshooting

### Common Issues

**No files found**

* Ensure correct directory selection
* Check supported file extensions (`.dcm`, `.avi`, `.jpg`)
* Verify directory contains the expected modality

**Processing errors**

* Check file permissions
* Ensure sufficient disk space
* Verify dependency installation

**Video playback issues**

* macOS: Uses **MJPG** codec for AVI compatibility
* Fallback to **XVID** codec if needed
* Ensure video files are not corrupted

### Log Interpretation

* ✅ Success messages
* ❌ Error messages (with details)
* ⚠️ Warnings (non-critical issues)
* → Processing details

---

## Development

### Code Structure

* `app_update.py` – Main GUI application
* `anonymize_common.py` – CT/MRI common processing
* `anonymize_ct.py` – CT-specific anonymization
* `anonymize_dicom.py` – DICOM ultrasound processing
* `anonymize_mri.py` – MRI-specific anonymization


The codebase uses a **modular design** for easy extension.

### Adding New Modalities

1. Create a new anonymization module
2. Add the modality to the UI selection
3. Implement processing logic
4. Add preview capabilities if needed

---

## Support

For issues, questions, or feature requests:

* Check the troubleshooting section
* Review the code documentation
* Contact the developer with specific details

---

## License and Attribution

* **Developer:** Zhuheng Li
* **Purpose:** Internal medical data anonymization
* **Restrictions:** Not for commercial distribution

### Disclaimer

This software is provided **“as is”**, without warranty of any kind.
It is designed to assist with medical data anonymization but does **not guarantee regulatory compliance**.
Users are responsible for verifying that processed data meets their institutional and legal requirements.

```

---

If you want next:
- a **shorter README** (GitHub-friendly)
- a **hospital / IRB / NIH-style** README
- or a **public open-source** version with badges

just say the word 👍
```
