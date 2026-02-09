import os
from anonymize_common import find_dicom_files, anonymize_dicom_file


def anonymize_ct_case(case_dir, log):
    """
    CT DICOM匿名化 - 自动搜索所有DICOM文件
    """
    log(f"\n=== Processing CT case ===")
    log(f"Directory: {case_dir}")

    # 查找所有DICOM文件
    dicom_files = find_dicom_files(case_dir, log)

    if not dicom_files:
        log(f"[WARN] No DICOM files found in {case_dir}")
        return 0

    log(f"Found {len(dicom_files)} DICOM files to process")

    # 处理每个DICOM文件
    count = 0
    for i, dicom_path in enumerate(dicom_files, 1):
        # log(f"\n[{i}/{len(dicom_files)}] Processing {os.path.basename(dicom_path)}...")

        if anonymize_dicom_file(dicom_path, "CT", log):
            count += 1

    log(f"\n=== CT Processing Complete ===")
    log(f"Successfully anonymized {count}/{len(dicom_files)} files")

    return count
