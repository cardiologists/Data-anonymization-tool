import os
import pydicom
from pydicom.errors import InvalidDicomError


def is_dicom(path):
    try:
        pydicom.dcmread(path, stop_before_pixels=True)
        return True
    except InvalidDicomError:
        return False
    except Exception:
        return False


def find_dicom_files(base_dir, log=None):
    """
    递归查找目录中的所有DICOM文件
    """
    dicom_files = []
    total_files = 0

    for root, dirs, files in os.walk(base_dir):
        for filename in files:
            total_files += 1
            filepath = os.path.join(root, filename)

            # 跳过明显的非DICOM文件
            if filename.lower().endswith(
                (
                    ".txt",
                    ".pdf",
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".bmp",
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                    ".py",
                    ".log",
                    ".ini",
                    ".cfg",
                    ".config",
                    ".bat",
                    ".sh",
                )
            ):
                continue

            # 检查文件大小
            try:
                if os.path.getsize(filepath) < 128:  # 太小不可能是DICOM
                    continue
            except:
                continue

            # 检查是否为DICOM
            if is_dicom(filepath):
                relative_path = os.path.relpath(filepath, base_dir)
                dicom_files.append(filepath)

                # if log:
                #     log(
                #         f"Found DICOM: {relative_path} ({os.path.getsize(filepath):,} bytes)"
                #     )

    if log:
        log(f"Scanned {total_files} files, found {len(dicom_files)} DICOM files")

    return dicom_files


def anonymize_dicom_file(dicom_path, modality="MRI", log=None):
    """
    通用DICOM匿名化函数
    """
    try:
        # if log:
        #     log(f"Processing: {os.path.basename(dicom_path)}")

        # 读取DICOM文件
        ds = pydicom.dcmread(dicom_path, force=True)

        # 通用匿名化字段（适用于所有模态）
        if hasattr(ds, "PatientName"):
            ds.PatientName = "ANON"

        if hasattr(ds, "PatientID"):
            ds.PatientID = "ANON_ID"

        if hasattr(ds, "PatientBirthDate"):
            ds.PatientBirthDate = ""

        if hasattr(ds, "PatientSex"):
            ds.PatientSex = ""

        if hasattr(ds, "InstitutionName"):
            ds.InstitutionName = ""

        if hasattr(ds, "ReferringPhysicianName"):
            ds.ReferringPhysicianName = ""

        if hasattr(ds, "PerformingPhysicianName"):
            ds.PerformingPhysicianName = ""

        if hasattr(ds, "OperatorsName"):
            ds.OperatorsName = ""

        # 特定于模态的匿名化
        if modality.upper() == "MRI":
            # MRI特定字段
            if hasattr(ds, "PatientAge"):
                ds.PatientAge = ""

            if hasattr(ds, "PatientSize"):
                ds.PatientSize = ""

            if hasattr(ds, "AdditionalPatientHistory"):
                ds.AdditionalPatientHistory = ""

            if hasattr(ds, "PatientComments"):
                ds.PatientComments = ""

            if hasattr(ds, "StationName"):
                ds.StationName = ""

            if hasattr(ds, "ProtocolName"):
                ds.ProtocolName = ""

            if hasattr(ds, "StudyID"):
                ds.StudyID = ""

            ds.DeidentificationMethod = "De-identified"
            ds.PatientIdentityRemoved = "YES"

        elif modality.upper() == "CT":
            # CT特定字段（通常较少）
            if hasattr(ds, "StudyID"):
                ds.StudyID = ""

            if hasattr(ds, "SeriesNumber"):
                # 保持序列号不变
                pass

        # 额外的通用匿名化
        extra_fields = [
            "PatientAddress",
            "PatientTelephoneNumbers",
            "OtherPatientIDs",
            "OtherPatientNames",
            "InstitutionAddress",
            "InstitutionalDepartmentName",
            "PhysicianOfRecord",
            "StudyDescription",
            "SeriesDescription",
        ]

        for field in extra_fields:
            if hasattr(ds, field):
                setattr(ds, field, "")

        # 保存文件
        ds.save_as(dicom_path)

        # if log:
        #     log(f"  ✓ Anonymized successfully")

        return True

    except Exception as e:
        if log:
            log(f"  ❌ Error: {str(e)}")
            import traceback

            log(f"  Traceback: {traceback.format_exc()}")
        return False
