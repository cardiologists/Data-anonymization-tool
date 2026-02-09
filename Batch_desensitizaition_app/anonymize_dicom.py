import os
import pydicom
from pydicom.tag import Tag
import traceback


def anonymize_ultrasound_dicom_complete(case_dir, log=None):
    """
    完全去匿名化 - 包括Weasis中显示的所有信息
    简化log输出，不显示具体PHI值
    """
    # 扩展PHI标签列表，确保覆盖所有时间相关标签
    PHI_TAGS = [
        # Patient Information
        (0x0010, 0x0010),  # PatientName
        (0x0010, 0x0020),  # PatientID
        (0x0010, 0x0030),  # PatientBirthDate
        (0x0010, 0x0040),  # PatientSex
        (0x0010, 0x1010),  # PatientAge
        # Study Information - 所有时间相关标签
        (0x0008, 0x0020),  # StudyDate
        (0x0008, 0x0021),  # SeriesDate
        (0x0008, 0x0022),  # AcquisitionDate  # ✅ Acq日期
        (0x0008, 0x0023),  # ContentDate
        (0x0008, 0x0030),  # StudyTime
        (0x0008, 0x0031),  # SeriesTime
        (0x0008, 0x0032),  # AcquisitionTime  # ✅ Acq时间
        (0x0008, 0x0033),  # ContentTime
        # 其他重要PHI
        (0x0008, 0x0080),  # InstitutionName
        (0x0008, 0x0090),  # ReferringPhysicianName
        (0x0008, 0x1070),  # OperatorsName
        (0x0008, 0x0081),  # InstitutionAddress
        (0x0008, 0x1040),  # InstitutionalDepartmentName
        (0x0008, 0x1048),  # PhysicianReadingStudy
        (0x0008, 0x1050),  # PerformingPhysicianName
        # Study/Series/Image Identifiers
        (0x0020, 0x000D),  # StudyInstanceUID
        (0x0020, 0x000E),  # SeriesInstanceUID
        (0x0020, 0x0010),  # StudyID
        (0x0020, 0x0011),  # SeriesNumber
        (0x0008, 0x0018),  # SOPInstanceUID
        # 设备信息（可能包含序列号）
        (0x0008, 0x0070),  # Manufacturer
        (0x0008, 0x1090),  # ManufacturerModelName
        (0x0018, 0x1000),  # DeviceSerialNumber
    ]

    # 定义标签名称映射（用于日志）
    TAG_NAMES = {
        (0x0008, 0x0022): "AcquisitionDate",
        (0x0008, 0x0032): "AcquisitionTime",
        (0x0008, 0x0080): "InstitutionName",
        (0x0010, 0x0010): "PatientName",
        (0x0010, 0x0020): "PatientID",
        (0x0010, 0x0030): "PatientBirthDate",
        (0x0010, 0x0040): "PatientSex",
        (0x0008, 0x0020): "StudyDate",
        (0x0008, 0x0030): "StudyTime",
        (0x0020, 0x0010): "StudyID",
    }

    files_processed = 0
    total_files = sum(
        1
        for root, _, files in os.walk(case_dir)
        for f in files
        if f.lower().endswith(".dcm")
    )

    if log:
        log(f"开始处理目录: {case_dir}")
        log(f"发现 {total_files} 个DICOM文件")

    for root, _, files in os.walk(case_dir):
        for f in files:
            if not f.lower().endswith(".dcm"):
                continue

            path = os.path.join(root, f)
            file_has_phi = False
            deleted_tags = []

            try:
                # ==================== 读取文件 ====================
                ds = pydicom.dcmread(path, force=True)

                # ==================== 检查并删除PHI ====================
                for tag_tuple in PHI_TAGS:
                    tag = Tag(tag_tuple)
                    if tag in ds:
                        tag_name = TAG_NAMES.get(tag_tuple, f"Tag{tag_tuple}")
                        deleted_tags.append(tag_name)

                        try:
                            del ds[tag]
                        except Exception:
                            # 如果删除失败，尝试设置为空或默认值
                            try:
                                if tag_tuple in [
                                    (0x0008, 0x0020),
                                    (0x0008, 0x0021),
                                    (0x0008, 0x0022),
                                    (0x0008, 0x0023),
                                ]:
                                    ds[tag].value = "19000101"  # 日期默认值
                                elif tag_tuple in [
                                    (0x0008, 0x0030),
                                    (0x0008, 0x0031),
                                    (0x0008, 0x0032),
                                    (0x0008, 0x0033),
                                ]:
                                    ds[tag].value = "000000"  # 时间默认值
                                elif tag_tuple == (0x0010, 0x0030):  # 出生日期
                                    ds[tag].value = "19000101"
                                elif tag_tuple == (0x0010, 0x0040):  # 性别
                                    ds[tag].value = "O"  # Other
                                elif tag_tuple == (0x0008, 0x0080):  # 机构名称
                                    ds[tag].value = "ANONYMIZED"
                                else:
                                    ds[tag].value = ""  # 其他设为空
                            except Exception:
                                pass  # 如果设置也失败，继续

                # ==================== 保存文件 ====================
                if deleted_tags:
                    file_has_phi = True
                    # 创建备份（可选）
                    backup_path = path + ".backup"
                    import shutil

                    shutil.copy2(path, backup_path)

                    # 保存修改后的文件
                    ds.save_as(path, write_like_original=True)

                    # 删除备份（如果需要保留备份，注释掉这行）
                    if os.path.exists(backup_path):
                        os.remove(backup_path)

                    files_processed += 1

                # ==================== 简化日志输出 ====================
                if log and file_has_phi:
                    log(f"✅ {f}: 已删除 {len(deleted_tags)} 个PHI标签")
                    # 如果需要详细标签信息（但不显示具体值）
                    if len(deleted_tags) <= 5:  # 标签少时显示
                        log(f"   删除的标签: {', '.join(deleted_tags)}")
                elif log and not file_has_phi:
                    log(f"ℹ️  {f}: 未发现PHI标签")

            except Exception as e:
                if log:
                    log(f"❌ {f}: 处理失败 - {str(e)[:100]}")  # 只显示前100字符

    # 总结报告
    if log:
        log(f"\n{'='*50}")
        log(f"处理完成")
        log(f"总文件数: {total_files}")
        log(f"已处理文件: {files_processed}")
        log(f"未发现PHI的文件: {total_files - files_processed}")

    return files_processed
