import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import queue
import cv2
from PIL import Image, ImageTk
from anonymize_mri import anonymize_mri_case
from anonymize_ct import anonymize_ct_case
from anonymize_dicom import anonymize_ultrasound_dicom_complete
import sys
import pydicom
from pydicom.errors import InvalidDicomError
import numpy as np


def resource_path(relative_path):
    """获取资源路径，PyInstaller 打包后也可用"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ================= DICOM anonymizer =================

""" Import from anonymize_dicom """

# ================= Video anonymizer =================


def anonymize_video(src, dst, direction, size, modality=None):
    """
    使用 OpenCV 处理视频遮罩，专门为 macOS 生成可播放的 AVI
    """
    # macOS 上生成可播放 AVI 的最佳编码器设置
    # 使用 MJPG 编码器，这是 macOS QuickTime 最兼容的 AVI 编码器
    codec = "MJPG"  # macOS 上最兼容的 AVI 编码器

    print(f"[DEBUG] Processing {os.path.basename(src)} with MJPG codec for macOS")

    try:
        # 读取视频
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {src}")

        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 1:
            fps = 30  # 默认帧率

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"[DEBUG] Input video: {width}x{height}, {fps}fps")

        size_value = int(size)

        # 根据 modality 设置最大比例
        max_ratio = 0.75

        if direction == "top":
            mask_px = min(size_value, int(height * max_ratio))
            mask_px = max(10, min(mask_px, height - 10))
        elif direction == "right":  # 右侧
            mask_px = min(size_value, int(width * max_ratio))
            mask_px = max(10, min(mask_px, width - 10))
        else:  # left - 新增左侧遮罩
            mask_px = min(size_value, int(width * max_ratio))
            mask_px = max(10, min(mask_px, width - 10))

        print(f"[DEBUG] Mask: {direction}, {mask_px}px")

        # 创建视频写入器 - 使用 MJPG 编码器和高质量设置
        fourcc = cv2.VideoWriter_fourcc(*codec)

        # macOS 上使用 .avi 扩展名，MJPG 编码器
        writer = cv2.VideoWriter(dst, fourcc, fps, (width, height), True)

        if not writer.isOpened():
            cap.release()
            # 如果默认设置失败，尝试其他兼容设置
            print(f"[DEBUG] First attempt failed, trying alternative settings...")
            writer = cv2.VideoWriter(dst, fourcc, fps, (width, height), isColor=True)

            if not writer.isOpened():
                # 最后尝试：如果宽度不是偶数，调整为偶数（MJPG要求）
                if width % 2 != 0:
                    width = width - 1
                if height % 2 != 0:
                    height = height - 1

                writer = cv2.VideoWriter(
                    dst, fourcc, fps, (width, height), isColor=True
                )

                if not writer.isOpened():
                    raise RuntimeError(f"Cannot create video writer with MJPG codec")

        frame_count = 0
        success = True

        while success:
            success, frame = cap.read()
            if not success:
                break

            frame_count += 1

            # 应用遮罩
            masked = frame.copy()
            if direction == "top":
                cv2.rectangle(masked, (0, 0), (width, mask_px), (0, 0, 0), -1)
            elif direction == "right":  # 右侧
                cv2.rectangle(
                    masked, (width - mask_px, 0), (width, height), (0, 0, 0), -1
                )
            else:  # left - 左侧
                cv2.rectangle(
                    masked,
                    (0, 0),
                    (mask_px, height),
                    (0, 0, 0),
                    -1,  # 这里需要添加left的处理
                )

            writer.write(masked)

        writer.release()
        cap.release()

        # 验证输出文件
        if frame_count == 0:
            raise RuntimeError("No frames processed")

        if not os.path.exists(dst):
            raise RuntimeError(f"Output file not created: {dst}")

        file_size = os.path.getsize(dst)
        print(
            f"[DEBUG] Created AVI file: {dst} ({file_size:,} bytes, {frame_count} frames)"
        )

        # 测试视频是否可以读取
        test_cap = cv2.VideoCapture(dst)
        if not test_cap.isOpened():
            raise RuntimeError("Output video cannot be opened")

        ret, test_frame = test_cap.read()
        test_cap.release()

        if not ret:
            raise RuntimeError("Output video is corrupted or unreadable")

        print(f"[DEBUG] ✓ Successfully created macOS-compatible AVI")
        return frame_count

    except Exception as e:
        print(f"[DEBUG] MJPG codec failed: {e}")

        # 如果 MJPG 失败，尝试 XVID 作为备用
        try:
            print(f"[DEBUG] Trying XVID as fallback...")
            return anonymize_video_fallback(src, dst, direction, size, modality)
        except Exception as e2:
            raise RuntimeError(
                f"Video processing failed. MJPG error: {e}, Fallback error: {e2}"
            )


def anonymize_video_fallback(src, dst, direction, size, modality=None):
    """
    XVID 备用方案
    """
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {src}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 1:
        fps = 30

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 确保尺寸是偶数（XVID要求）
    if width % 2 != 0:
        width = width - 1
    if height % 2 != 0:
        height = height - 1

    # # 计算遮罩
    # if modality == "Intracardiac Echo (ICE)":
    #     max_ratio = 0.75
    # elif modality == "Transthoracic Echo (TTE)":
    #     max_ratio = 0.75
    # else:
    #     max_ratio = 0.75
    max_ratio = 0.75

    size_value = int(size)
    if direction == "top":
        mask_px = min(size_value, int(height * max_ratio))
        mask_px = max(10, min(mask_px, height - 10))
    else:
        mask_px = min(size_value, int(width * max_ratio))
        mask_px = max(10, min(mask_px, width - 10))

    # 使用 XVID 编码器
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    writer = cv2.VideoWriter(dst, fourcc, fps, (width, height), True)

    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Cannot create video writer with XVID codec")

    frame_count = 0
    success = True

    while success:
        success, frame = cap.read()
        if not success:
            break

        frame_count += 1

        # 调整帧尺寸
        frame = cv2.resize(frame, (width, height))

        # 应用遮罩
        masked = frame.copy()
        if direction == "top":
            cv2.rectangle(masked, (0, 0), (width, mask_px), (0, 0, 0), -1)
        elif direction == "right":  # 右侧
            cv2.rectangle(masked, (width - mask_px, 0), (width, height), (0, 0, 0), -1)
        else:  # left - 左侧
            cv2.rectangle(
                masked, (0, 0), (mask_px, height), (0, 0, 0), -1
            )  # 这里需要添加left的处理

        writer.write(masked)

    writer.release()
    cap.release()

    if frame_count == 0:
        raise RuntimeError("No frames processed")

    if not os.path.exists(dst):
        raise RuntimeError(f"Output file not created: {dst}")

    file_size = os.path.getsize(dst)
    print(
        f"[DEBUG] Created XVID AVI: {dst} ({file_size:,} bytes, {frame_count} frames)"
    )

    return frame_count


# ================= Video Preview Window =================


class VideoPreviewWindow(tk.Toplevel):
    def __init__(
        self, parent, video_path, init_cfg, on_confirm, first_frame=None, modality=None
    ):
        super().__init__(parent)
        self.title("Ultrasound Video Preview")
        self.geometry("1100x750")
        self.minsize(900, 600)
        self.transient(parent)  # 弹窗在父窗口上
        self.grab_set()  # 模态
        self.focus_force()

        self.video_path = video_path
        self.on_confirm = on_confirm
        self.mask_direction = tk.StringVar(value=init_cfg["direction"])
        self.mask_size = tk.IntVar(value=init_cfg["size"])
        self.modality = modality
        self.max_value = 3000

        if first_frame is not None:
            self.base_frame = first_frame
        else:
            cap = cv2.VideoCapture(self.video_path)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                raise RuntimeError("Cannot read preview frame")
            self.base_frame = frame

        self.frame_h, self.frame_w = self.base_frame.shape[:2]

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        self._resize_job = None
        self._build_preview()
        self._build_controls()

        self.mask_size.trace_add("write", self._on_mask_size_entry_changed)

        self.bind("<Configure>", self._on_resize)
        self.update_preview()

    def _build_preview(self):
        frame = ttk.Frame(self)
        frame.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas = tk.Canvas(frame, background="#d9d9d9")
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_canvas.image_ref = None

    def _build_controls(self):
        ctrl = ttk.Frame(self, padding=12, relief="ridge")
        ctrl.grid(row=1, column=0, sticky="ew")
        ctrl.columnconfigure(0, weight=1)

        right_box = ttk.Frame(ctrl)
        right_box.grid(row=0, column=0, sticky="e")

        ttk.Label(right_box, text="Mask direction:").grid(row=0, column=0, padx=5)

        ttk.Radiobutton(
            right_box,
            text="Left",
            variable=self.mask_direction,
            value="left",
            command=self._on_direction_changed,
        ).grid(row=0, column=1, padx=5)

        ttk.Radiobutton(
            right_box,
            text="Top",
            variable=self.mask_direction,
            value="top",
            command=self._on_direction_changed,
        ).grid(row=0, column=2, padx=5)

        ttk.Radiobutton(
            right_box,
            text="Right",
            variable=self.mask_direction,
            value="right",
            command=self._on_direction_changed,
        ).grid(row=0, column=3, padx=5)

        ttk.Label(right_box, text="Mask size (px):").grid(row=0, column=4, padx=(15, 5))

        self._update_scale_max_value()

        self.mask_size_scale = ttk.Scale(
            right_box,
            from_=1,
            to=self.max_value,  # 使用动态计算的最大值
            orient="horizontal",
            command=self._on_mask_size_scale_changed,
        )
        self.mask_size_scale.set(min(self.mask_size.get(), self.max_value))
        self.mask_size_scale.grid(row=0, column=5, padx=5, sticky="ew")

        self.mask_size_entry = ttk.Entry(
            right_box,
            width=6,
            textvariable=self.mask_size,
        )
        self.mask_size_entry.grid(row=0, column=6, padx=(5, 5))

        ttk.Label(right_box, text="px").grid(row=0, column=7, padx=(0, 15))

        ttk.Button(
            right_box,
            text="Confirm",
            command=self.confirm,
        ).grid(row=0, column=8, padx=(15, 0))

    def _on_direction_changed(self):
        """方向改变时更新滑块的最大值"""
        self._update_scale_max_value()
        self.mask_size_scale.config(to=self.max_value)

        # 确保当前值不超过新的最大值
        current_val = self.mask_size.get()
        if current_val > self.max_value:
            self.mask_size.set(self.max_value)

        self.update_preview()

    def _update_scale_max_value(self):
        """根据方向和模态计算滑块的最大值"""
        direction = self.mask_direction.get()

        if self.modality in ("Intracardiac Echo (ICE)", "Transthoracic Echo (TTE)"):
            max_ratio = 0.75  # 最大75%

            if direction == "top":
                # 上方遮罩：最大为高度的75%
                self.max_value = int(self.frame_h * max_ratio)
            else:
                # 左侧或右侧遮罩：最大为宽度的75%
                self.max_value = int(self.frame_w * max_ratio)
        else:
            self.max_value = 3000

        # 确保最小值
        self.max_value = max(10, self.max_value)

    def _on_resize(self, _=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self.update_preview)

    def _on_mask_size_entry_changed(self, *_):
        val = self.mask_size.get()

        if val in ("", None):
            return

        try:
            size = int(val)
        except Exception:
            return

        size = max(1, min(size, 3000))

        if int(self.mask_size_scale.get()) != size:
            self.mask_size_scale.set(size)

        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(30, self.update_preview)

    def _on_mask_size_scale_changed(self, value):
        size = int(float(value))
        self.mask_size.set(size)

        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(30, self.update_preview)

    def update_preview(self):
        if self.base_frame is None:
            return

        orig_h, orig_w = self.base_frame.shape[:2]

        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1:
            return

        scale = min(canvas_w / orig_w, canvas_h / orig_h)
        disp_w = int(orig_w * scale)
        disp_h = int(orig_h * scale)

        frame = cv2.resize(self.base_frame, (disp_w, disp_h))

        size_value = self.mask_size.get()

        # 根据 modality 设置最大比例
        # if self.modality == "Intracardiac Echo (ICE)":
        #     max_ratio = 0.75  # 改为75%
        # elif self.modality == "Transthoracic Echo (TTE)":
        #     max_ratio = 0.75  # 改为75%
        # else:
        #     max_ratio = 1.0
        max_ratio = 0.75

        direction = self.mask_direction.get()

        if direction == "top":
            mask_px_by_value = max(1, min(int(size_value), int(orig_h * max_ratio)))
            mask_px_disp = int(mask_px_by_value * disp_h / orig_h)
            x1, y1, x2, y2 = 0, 0, disp_w, mask_px_disp
        elif direction == "right":
            mask_px_by_value = max(1, min(int(size_value), int(orig_w * max_ratio)))
            mask_px_disp = int(mask_px_by_value * disp_w / orig_w)
            x1, y1, x2, y2 = disp_w - mask_px_disp, 0, disp_w, disp_h
        else:  # left
            mask_px_by_value = max(1, min(int(size_value), int(orig_w * max_ratio)))
            mask_px_disp = int(mask_px_by_value * disp_w / orig_w)
            x1, y1, x2, y2 = 0, 0, mask_px_disp, disp_h  # 左侧遮罩

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (120, 120, 120), -1)
        frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 2)

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        self.tk_img = ImageTk.PhotoImage(img)

        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            canvas_w // 2,
            canvas_h // 2,
            image=self.tk_img,
            anchor="center",
        )
        self.preview_canvas.image_ref = self.tk_img

    def confirm(self):
        self.on_confirm(
            {
                "direction": self.mask_direction.get(),
                "size": self.mask_size.get(),
            }
        )
        self.destroy()


# ================= JPEG Preview Window =================


# ================= JPEG Preview Window (Simplified) =================


class JPEGPreviewWindow(tk.Toplevel):
    """简化版JPEG图像水印去除预览窗口"""

    def __init__(self, parent, image_path, mask_regions, on_confirm, first_frame=None):
        super().__init__(parent)
        self.title("JPEG Watermark Mask Configuration")
        self.geometry("1000x700")
        self.minsize(800, 600)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        self.image_path = image_path
        self.on_confirm = on_confirm
        self.mask_regions = mask_regions.copy() if mask_regions else []

        if first_frame is not None:
            self.base_frame = first_frame.copy()
        else:
            self.base_frame = safe_imread(image_path)
            if self.base_frame is None:
                raise RuntimeError("Cannot read JPEG image")

        self.frame_h, self.frame_w = self.base_frame.shape[:2]
        self.current_region = None
        self.drawing = False
        self.selected_region_idx = -1
        self.drag_start = None

        # 坐标转换参数
        self.scale_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0

        # 设置窗口布局
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)  # 图片区域占主要空间
        self.rowconfigure(1, weight=0)  # 工具栏区域

        self._resize_job = None
        self._build_preview_area()
        self._build_simple_toolbar()

        self.bind("<Configure>", self._on_resize)
        self.update_preview()

    def _build_preview_area(self):
        """构建图片预览区域"""
        frame = ttk.Frame(self)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 画布
        self.preview_canvas = tk.Canvas(frame, background="#333333", cursor="crosshair")
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_canvas.image_ref = None

        # 绑定鼠标事件
        self.preview_canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.preview_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.preview_canvas.bind("<Motion>", self.on_mouse_move)

    def _build_simple_toolbar(self):
        """构建简化工具栏"""
        toolbar = ttk.Frame(self, relief="ridge", padding=8)
        toolbar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        # 左侧：工具选择
        left_frame = ttk.Frame(toolbar)
        left_frame.pack(side="left", fill="y")

        ttk.Label(left_frame, text="Tool:").pack(side="left", padx=(0, 5))

        self.tool_var = tk.StringVar(value="draw")
        ttk.Radiobutton(
            left_frame, text="Draw", variable=self.tool_var, value="draw"
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            left_frame, text="Select", variable=self.tool_var, value="select"
        ).pack(side="left", padx=5)

        # 中间：区域信息
        center_frame = ttk.Frame(toolbar)
        center_frame.pack(side="left", fill="y", padx=20)

        self.info_label = ttk.Label(
            center_frame, text=f"Regions: {len(self.mask_regions)}"
        )
        self.info_label.pack(side="left")

        # 右侧：操作按钮
        right_frame = ttk.Frame(toolbar)
        right_frame.pack(side="right", fill="y")

        ttk.Button(
            right_frame,
            text="Delete Selected",
            command=self.delete_selected_region,
            width=15,
        ).pack(side="left", padx=3)

        ttk.Button(
            right_frame, text="Clear All", command=self.clear_all_regions, width=15
        ).pack(side="left", padx=3)

        ttk.Button(
            right_frame, text="Apply to All JPEGs", command=self.confirm, width=15
        ).pack(side="left", padx=3)

        ttk.Button(right_frame, text="Cancel", command=self.destroy, width=10).pack(
            side="left", padx=3
        )

    def _on_resize(self, _=None):
        """窗口大小改变时重新计算显示参数"""
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(100, self._calculate_display_params)

    def _calculate_display_params(self):
        """计算显示参数（居中、缩放）"""
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()

        if canvas_w <= 1 or canvas_h <= 1:
            return

        # 计算缩放比例（保持宽高比）
        scale_w = canvas_w / self.frame_w
        scale_h = canvas_h / self.frame_h
        self.scale_factor = min(scale_w, scale_h)

        # 计算居中偏移
        disp_w = int(self.frame_w * self.scale_factor)
        disp_h = int(self.frame_h * self.scale_factor)
        self.offset_x = (canvas_w - disp_w) // 2
        self.offset_y = (canvas_h - disp_h) // 2

        self.update_preview()

    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """画布坐标转图像坐标"""
        if self.scale_factor <= 0:
            return 0, 0

        # 减去偏移，除以缩放比例
        img_x = int((canvas_x - self.offset_x) / self.scale_factor)
        img_y = int((canvas_y - self.offset_y) / self.scale_factor)

        # 限制在图像范围内
        img_x = max(0, min(img_x, self.frame_w - 1))
        img_y = max(0, min(img_y, self.frame_h - 1))

        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        """图像坐标转画布坐标"""
        canvas_x = int(img_x * self.scale_factor) + self.offset_x
        canvas_y = int(img_y * self.scale_factor) + self.offset_y
        return canvas_x, canvas_y

    def on_mouse_down(self, event):
        """鼠标按下"""
        mode = self.tool_var.get()

        if mode == "draw":
            # 开始绘制新区域
            self.drawing = True
            img_x, img_y = self.canvas_to_image_coords(event.x, event.y)
            canvas_x, canvas_y = self.image_to_canvas_coords(img_x, img_y)
            self.current_region = [canvas_x, canvas_y, canvas_x, canvas_y]

        elif mode == "select":
            # 检查是否点击了已有区域
            img_x, img_y = self.canvas_to_image_coords(event.x, event.y)

            for i, region in enumerate(self.mask_regions):
                x1, y1, x2, y2 = region
                if x1 <= img_x <= x2 and y1 <= img_y <= y2:
                    self.selected_region_idx = i
                    # 保存拖动起始信息
                    self.drag_start = (event.x, event.y, x1, y1, x2, y2)
                    self.update_preview()
                    break

    def on_mouse_drag(self, event):
        """鼠标拖动"""
        mode = self.tool_var.get()

        if mode == "draw" and self.drawing and self.current_region:
            # 更新矩形结束点
            self.current_region[2] = event.x
            self.current_region[3] = event.y
            self.update_preview()

        elif mode == "select" and self.drag_start and self.selected_region_idx >= 0:
            # 拖动选中的区域
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]

            if self.scale_factor > 0:
                dx_img = int(dx / self.scale_factor)
                dy_img = int(dy / self.scale_factor)

                x1 = self.drag_start[2] + dx_img
                y1 = self.drag_start[3] + dy_img
                x2 = self.drag_start[4] + dx_img
                y2 = self.drag_start[5] + dy_img

                # 限制在图像范围内
                x1 = max(0, min(x1, self.frame_w))
                y1 = max(0, min(y1, self.frame_h))
                x2 = max(0, min(x2, self.frame_w))
                y2 = max(0, min(y2, self.frame_h))

                self.mask_regions[self.selected_region_idx] = (x1, y1, x2, y2)
                self.update_preview()

    def on_mouse_up(self, event):
        """鼠标释放"""
        mode = self.tool_var.get()

        if mode == "draw" and self.drawing and self.current_region:
            self.drawing = False

            # 获取画布坐标
            start_x, start_y = self.current_region[0], self.current_region[1]
            end_x, end_y = event.x, event.y

            # 转换到图像坐标
            x1_img, y1_img = self.canvas_to_image_coords(start_x, start_y)
            x2_img, y2_img = self.canvas_to_image_coords(end_x, end_y)

            # 确保坐标顺序正确
            x1_img, x2_img = sorted([x1_img, x2_img])
            y1_img, y2_img = sorted([y1_img, y2_img])

            # 确保区域足够大
            if abs(x2_img - x1_img) > 5 and abs(y2_img - y1_img) > 5:
                self.mask_regions.append((x1_img, y1_img, x2_img, y2_img))
                self.info_label.config(text=f"Regions: {len(self.mask_regions)}")

            self.current_region = None
            self.update_preview()

        elif mode == "select":
            self.drag_start = None

    def on_mouse_move(self, event):
        """鼠标移动"""
        mode = self.tool_var.get()

        if mode == "select":
            # 检查是否在区域内，改变光标
            img_x, img_y = self.canvas_to_image_coords(event.x, event.y)
            in_region = False

            for region in self.mask_regions:
                x1, y1, x2, y2 = region
                if x1 <= img_x <= x2 and y1 <= img_y <= y2:
                    in_region = True
                    break

            self.preview_canvas.config(cursor="hand2" if in_region else "arrow")
        else:
            self.preview_canvas.config(cursor="crosshair")

    def update_preview(self):
        """更新预览显示"""
        if self.base_frame is None or self.scale_factor <= 0:
            return

        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()

        if canvas_w <= 1 or canvas_h <= 1:
            return

        # 创建灰色背景
        canvas_image = np.ones((canvas_h, canvas_w, 3), dtype=np.uint8) * 128

        # 计算显示尺寸
        disp_w = int(self.frame_w * self.scale_factor)
        disp_h = int(self.frame_h * self.scale_factor)

        # 缩放图像并放置在中央
        resized_frame = cv2.resize(self.base_frame, (disp_w, disp_h))
        canvas_image[
            self.offset_y : self.offset_y + disp_h,
            self.offset_x : self.offset_x + disp_w,
        ] = resized_frame

        # 应用黑色遮罩
        for i, region in enumerate(self.mask_regions):
            x1, y1, x2, y2 = region

            # 转换到画布坐标
            x1_canvas, y1_canvas = self.image_to_canvas_coords(x1, y1)
            x2_canvas, y2_canvas = self.image_to_canvas_coords(x2, y2)

            # 绘制黑色矩形
            cv2.rectangle(
                canvas_image,
                (x1_canvas, y1_canvas),
                (x2_canvas, y2_canvas),
                (0, 0, 0),
                -1,  # 填充
            )

            # 绘制边框（选中区域用绿色，其他用红色）
            border_color = (0, 255, 0) if i == self.selected_region_idx else (255, 0, 0)
            cv2.rectangle(
                canvas_image,
                (x1_canvas, y1_canvas),
                (x2_canvas, y2_canvas),
                border_color,
                2,
            )

        # 绘制当前正在绘制的矩形（半透明黄色边框）
        if self.current_region and self.drawing:
            x1, y1, x2, y2 = self.current_region
            cv2.rectangle(canvas_image, (x1, y1), (x2, y2), (0, 255, 255), 2)

        # 显示到画布
        canvas_image = cv2.cvtColor(canvas_image, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(canvas_image)
        self.tk_img = ImageTk.PhotoImage(img)

        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            canvas_w // 2,
            canvas_h // 2,
            image=self.tk_img,
            anchor="center",
        )
        self.preview_canvas.image_ref = self.tk_img

    def delete_selected_region(self):
        """删除选中的区域"""
        if 0 <= self.selected_region_idx < len(self.mask_regions):
            del self.mask_regions[self.selected_region_idx]
            self.selected_region_idx = -1
            self.info_label.config(text=f"Regions: {len(self.mask_regions)}")
            self.update_preview()

    def clear_all_regions(self):
        """清除所有区域"""
        self.mask_regions = []
        self.selected_region_idx = -1
        self.info_label.config(text=f"Regions: {len(self.mask_regions)}")
        self.update_preview()

    def confirm(self):
        """确认配置"""
        self.on_confirm(
            {"regions": self.mask_regions.copy(), "method": "black"}  # 固定为黑色填充
        )
        self.destroy()


# ================= Main App =================


class BatchAnonymizationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Batch Medical Data Desensitization")
        self.center_window(620, 620)
        self.root.resizable(True, True)

        self.keep_original = tk.BooleanVar(value=True)

        self.input_dir = tk.StringVar()
        self.modality = tk.StringVar(value="")
        self.video_mask_cfg = {"direction": "top", "size": 80}
        self.stop_requested = False

        self._found_video = None
        self._found_first_frame = None

        self._found_jpeg = None
        self._found_first_jpeg_frame = None
        self.jpeg_mask_cfg = {"regions": [], "method": "black"}

        self.ui_queue = queue.Queue()
        self._ui_polling = False

        self._build_ui()
        self._schedule_ui_queue()

    def _schedule_ui_queue(self):
        if not self._ui_polling:
            self._ui_polling = True
            self.root.after(50, self._process_ui_queue)

    def _process_ui_queue(self):
        processed = 0
        try:
            while processed < 3:
                msg = self.ui_queue.get_nowait()
                processed += 1

                kind = msg[0]

                if kind == "log":
                    self.append_log(msg[1])

                elif kind == "progress":
                    _, percent, case = msg
                    self._update_progress_ui(percent, case)

                elif kind == "status":
                    _, text, color = msg
                    self.status_label.config(text=text, foreground=color)

                elif kind == "done":
                    self._on_batch_finished()

                elif kind == "video_found":
                    _, video, frame = msg
                    self._on_video_found(video, frame)

                elif kind == "jpeg_found":
                    _, jpeg_path, frame = msg
                    self._on_jpeg_found(jpeg_path, frame)

        except queue.Empty:
            pass

        if not self.ui_queue.empty():
            self.root.after(30, self._process_ui_queue)
        else:
            self._ui_polling = False

    def _on_jpeg_mask_confirmed(self, mask_cfg):
        """JPEG遮罩配置确认回调"""
        self.jpeg_mask_cfg = mask_cfg
        self.status_label.config(
            text=f"✓ JPEG mask configured: {len(mask_cfg['regions'])} regions, method: {mask_cfg['method']}",
            foreground="green",
        )
        self.ui_queue.put(
            ("log", f"JPEG mask configured: {len(mask_cfg['regions'])} regions")
        )

    def _on_video_found(self, video, first_frame):
        self.spinner.stop()
        self.spinner.pack_forget()

        if not video or first_frame is None:
            self.status_label.config(
                text="❌ No ultrasound AVI found or failed to read",
                foreground="red",
            )
            self.preview_btn.config(state="disabled")
            return

        self._found_video = video
        self._found_first_frame = first_frame

        self.status_label.config(
            text="Ultrasound video found. Click Preview to view.",
            foreground="green",
        )
        self.preview_btn.config(state="normal")

    def center_window(self, width, height):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = int((screen_w - width) / 2)
        y = int((screen_h - height) / 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self):
        ttk.Label(
            self.root,
            text="Batch Medical Data Desensitization --- 医疗数据除敏批处理",
            font=("Helvetica", 16, "bold"),
        ).pack(pady=15)

        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=15)

        ttk.Label(frame, text="Input Directory/批文件路径").pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=5)

        ttk.Entry(row, textvariable=self.input_dir).pack(
            side="left", fill="x", expand=True
        )

        self.keep_original_chk = ttk.Checkbutton(
            frame,
            text="Keep original data (output to *_anon)",
            variable=self.keep_original,
        )
        self.keep_original_chk.pack(anchor="w", pady=(6, 0))

        self.browse_btn = ttk.Button(row, text="Browse", command=self.browse)
        self.browse_btn.pack(side="left", padx=5)

        ttk.Label(frame, text="Modality/修改项目").pack(anchor="w", pady=(12, 2))
        modality_frame = ttk.Frame(frame)
        modality_frame.pack(fill="x")

        self.modality_combo = ttk.Combobox(
            modality_frame,
            textvariable=self.modality,
            values=[
                "MRI",
                "CT",
                "Intracardiac Echo (ICE)",
                "Transthoracic Echo (TTE)",
                "Ultrasound DICOM",
            ],
            state="readonly",
        )
        self.modality_combo.pack(fill="x")
        self.modality_combo.bind("<<ComboboxSelected>>", self.on_modality_selected)

        self.preview_btn = ttk.Button(
            modality_frame,
            text="Preview ultrasound mask…",
            command=self.on_preview_clicked,
            state="disabled",
        )
        self.preview_btn.pack(fill="x", pady=(6, 0))

        self.status_label = ttk.Label(frame, text="", foreground="gray")
        self.status_label.pack(pady=(8, 0))

        self.spinner = ttk.Progressbar(frame, mode="indeterminate")

        prog = ttk.LabelFrame(frame, text="Progress")
        prog.pack(fill="x", pady=12)

        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.pack(fill="x", pady=(5, 0))

        self.progress_label = ttk.Label(prog, text="0%")
        self.progress_label.pack()

        self.current_case_label = ttk.Label(prog, text="Waiting...", foreground="gray")
        self.current_case_label.pack()

        log_frame = ttk.LabelFrame(frame, text="Output")
        log_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.log_text = tk.Text(log_frame, height=10, wrap="none")
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")

        self.log_text.configure(yscrollcommand=scrollbar.set, state="disabled")

        btns = ttk.Frame(frame)
        btns.pack(pady=15)

        ttk.Button(btns, text="Run", command=self.start).pack(side="left", padx=6)
        ttk.Button(btns, text="Stop", command=self.stop).pack(side="left", padx=6)

        self.exit_btn = ttk.Button(
            btns, text="Exit", command=self.on_exit, state="disabled"
        )
        self.exit_btn.pack(side="left", padx=5)

    def browse(self):
        d = filedialog.askdirectory(parent=self.root)
        if d:
            self.input_dir.set(d)
        self.root.after(50, lambda: self.modality_combo.focus_force())

    def on_modality_selected(self, _=None):
        selected = self.modality.get()

        if selected in ["MRI", "CT"]:
            # MRI和CT模式 - 启用JPEG预览
            self.preview_btn.config(
                text="Preview & Configure Mask...",
                state="normal" if self.input_dir.get() else "disabled",
            )
            self.status_label.config(
                text="⚠️ MRI/CT data includes JPEG images. Click 'Preview' to configure mask regions.",
                foreground="orange",
            )

            # 查找JPEG样本
            if self.input_dir.get():
                threading.Thread(target=self._find_jpeg_sample, daemon=True).start()
            else:
                self.status_label.config(
                    text="Please select input directory first", foreground="gray"
                )

        elif selected in ("Intracardiac Echo (ICE)", "Transthoracic Echo (TTE)"):
            if not self.input_dir.get():
                self.preview_btn.config(state="disabled")
                self.status_label.config(
                    text="Please select input directory first",
                    foreground="gray",
                )
                return

            self.preview_btn.config(state="disabled")
            self.status_label.config(
                text="Finding ultrasound video…",
                foreground="gray",
            )
            self.spinner.pack(pady=5)
            self.spinner.start(10)

            self._found_video = None
            self._found_first_frame = None

            threading.Thread(target=self._find_video, daemon=True).start()

        else:
            self.preview_btn.config(state="disabled")
            self.status_label.config(text="", foreground="gray")

    def _on_mask_confirmed(self, mask_cfg):
        self.video_mask_cfg = mask_cfg
        self.status_label.config(
            text="Ultrasound mask confirmed",
            foreground="green",
        )

    def on_preview_clicked(self):
        """预览按钮点击事件"""
        selected = self.modality.get()

        if selected in ["MRI", "CT"]:
            # JPEG预览
            if not self._found_jpeg or self._found_first_jpeg_frame is None:
                messagebox.showwarning("Warning", "No JPEG files found to preview")
                return

            JPEGPreviewWindow(
                self.root,
                self._found_jpeg,
                self.jpeg_mask_cfg.get("regions", []),
                self._on_jpeg_mask_confirmed,
                self._found_first_jpeg_frame,
            )

        elif selected in ("Intracardiac Echo (ICE)", "Transthoracic Echo (TTE)"):
            # 原有的超声视频预览
            if not self._found_video or self._found_first_frame is None:
                return

            VideoPreviewWindow(
                self.root,
                self._found_video,
                self.video_mask_cfg,
                self._on_mask_confirmed,
                self._found_first_frame,
                modality=self.modality.get(),
            )

    def _find_video(self):
        video = None
        for r, _, fs in os.walk(self.input_dir.get()):
            for f in fs:
                if f.lower().endswith(".avi"):
                    video = os.path.join(r, f)
                    break
            if video:
                break

        if not video:
            self.ui_queue.put(("video_found", None, None))
            self._schedule_ui_queue()
            return

        cap = cv2.VideoCapture(video)
        ret, frame = cap.read()
        cap.release()

        self.ui_queue.put(("video_found", video, frame if ret else None))
        self._schedule_ui_queue()

    def _find_jpeg_sample(self):
        """在MRI/CT目录中查找JPEG文件作为样本"""
        jpeg_path = None
        sample_image = None

        # 查找exam/jpeg目录
        target_dir = self.input_dir.get()

        # 检查是否存在exam/jpeg目录
        jpeg_dir = os.path.join(target_dir, "exam", "jpeg")

        if os.path.exists(jpeg_dir) and os.path.isdir(jpeg_dir):
            # 查找第一个JPEG文件
            for f in os.listdir(jpeg_dir):
                if f.lower().endswith((".jpg", ".jpeg")):
                    jpeg_path = os.path.join(jpeg_dir, f)
                    try:
                        # 读取图片
                        img = safe_imread(jpeg_path)
                        if img is not None:
                            sample_image = img
                            break
                    except:
                        continue

        # 如果没有找到，在目录中搜索任何JPEG文件
        if not jpeg_path:
            for root, dirs, files in os.walk(target_dir):
                for f in files:
                    if f.lower().endswith((".jpg", ".jpeg")):
                        jpeg_path = os.path.join(root, f)
                        try:
                            img = safe_imread(jpeg_path)
                            if img is not None:
                                sample_image = img
                                break
                        except:
                            continue
                if jpeg_path:
                    break

        # 更新UI
        self.ui_queue.put(("jpeg_found", jpeg_path, sample_image))
        self._schedule_ui_queue()

    def _on_jpeg_found(self, jpeg_path, sample_image):
        """JPEG样本找到后的处理"""
        if not jpeg_path or sample_image is None:
            self.status_label.config(
                text="No JPEG files found in the selected directory", foreground="gray"
            )
            self.preview_btn.config(state="disabled")
            return

        self._found_jpeg = jpeg_path
        self._found_first_jpeg_frame = sample_image

        # 获取目录中JPEG文件总数
        jpeg_count = 0
        for root, dirs, files in os.walk(self.input_dir.get()):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg")):
                    jpeg_count += 1

        if jpeg_count > 0:
            self.status_label.config(
                text=f"✓ Found {jpeg_count} JPEG files. Click 'Preview' to configure mask regions.",
                foreground="green",
            )
            self.preview_btn.config(state="normal")
        else:
            self.status_label.config(
                text="No JPEG files found in the selected directory", foreground="gray"
            )
            self.preview_btn.config(state="disabled")

    def append_log(self, msg: str):
        if not msg:
            return

        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_progress_ui(self, percent, case_name):
        try:
            percent = int(percent)
        except Exception:
            percent = 0

        percent = max(0, min(100, percent))

        self.progress["value"] = percent
        self.progress_label.config(text=f"{percent}%")

        if case_name:
            self.current_case_label.config(
                text=f"Processing: {case_name}",
                foreground="black",
            )
        else:
            self.current_case_label.config(
                text="Processing…",
                foreground="gray",
            )

    def start(self):
        if not self.input_dir.get():
            messagebox.showwarning("Warning", "Please select input directory first")
            return

        self.stop_requested = False

        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")

        self.progress["value"] = 0
        self.progress_label.config(text="0%")
        self.current_case_label.config(text="Starting...", foreground="black")
        self.exit_btn.config(state="disabled")

        self.ui_queue.put(
            ("log", f"Starting batch processing for modality: {self.modality.get()}")
        )
        self.ui_queue.put(("log", f"Input directory: {self.input_dir.get()}"))
        self.ui_queue.put(("log", f"Mask configuration: {self.video_mask_cfg}"))
        self._schedule_ui_queue()

        threading.Thread(target=self.run_batch, daemon=True).start()

    def stop(self):
        self.stop_requested = True
        self.ui_queue.put(("status", "Stopping after current file…", "orange"))
        self._schedule_ui_queue()

    def process_jpeg_files(self, case_dir):
        """处理目录中的所有JPEG文件"""
        jpeg_count = 0

        # 查找所有JPEG文件
        jpeg_files = []
        for root, dirs, files in os.walk(case_dir):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg")):
                    jpeg_files.append(os.path.join(root, f))

        if not jpeg_files:
            return 0

        self.ui_queue.put(("log", f"Found {len(jpeg_files)} JPEG files to process"))

        for i, jpeg_path in enumerate(jpeg_files, 1):
            if self.stop_requested:
                break

            try:
                # 读取图片
                img = safe_imread(jpeg_path)
                if img is None:
                    continue

                height, width = img.shape[:2]
                result = img.copy()

                # 应用所有遮罩区域
                for region in self.jpeg_mask_cfg.get("regions", []):
                    x1, y1, x2, y2 = region

                    # 确保区域在图像范围内
                    x1 = max(0, min(x1, width))
                    y1 = max(0, min(y1, height))
                    x2 = max(0, min(x2, width))
                    y2 = max(0, min(y2, height))

                    method = self.jpeg_mask_cfg.get("method", "black")

                    if method == "black":
                        cv2.rectangle(result, (x1, y1), (x2, y2), (0, 0, 0), -1)
                    elif method == "blur":
                        roi = result[y1:y2, x1:x2]
                        if roi.size > 0:
                            blurred = cv2.GaussianBlur(roi, (51, 51), 0)
                            result[y1:y2, x1:x2] = blurred
                    elif method == "inpaint":
                        mask = np.zeros((height, width), dtype=np.uint8)
                        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
                        result = cv2.inpaint(result, mask, 3, cv2.INPAINT_TELEA)

                # 保存结果
                safe_imwrite(jpeg_path, result)
                jpeg_count += 1

                # if i % 50 == 0:  # 每处理50个文件报告一次
                #     self.ui_queue.put(
                #         ("log", f"  Processed {i}/{len(jpeg_files)} JPEG files")
                #     )

            except Exception as e:
                self.ui_queue.put(
                    (
                        "log",
                        f"  ❌ Error processing {os.path.basename(jpeg_path)}: {str(e)}",
                    )
                )

        return jpeg_count

    def run_batch(self):
        src_root = self.input_dir.get()

        # =========== 添加 DICOM 检测函数 ===========
        def is_dicom_quick(filepath):
            """快速检查是否为DICOM文件（优化版）"""
            try:
                if not os.path.isfile(filepath):
                    return False

                # 检查文件大小
                file_size = os.path.getsize(filepath)
                if file_size < 132:  # DICOM文件最小大小
                    return False

                # 方法1：快速检查DICOM前缀（128字节后）
                with open(filepath, "rb") as f:
                    f.seek(128)
                    prefix = f.read(4)
                    if prefix == b"DICM":
                        return True

                # 方法2：检查文件扩展名（如果有）
                filename_lower = filepath.lower()
                if filename_lower.endswith((".dcm", ".dic", ".dicom")):
                    # 有DICOM扩展名，尝试用pydicom验证
                    try:
                        pydicom.dcmread(filepath, stop_before_pixels=True, force=True)
                        return True
                    except:
                        return False

                # 方法3：对于没有明显标识的文件，跳过常见非DICOM文件
                filename = os.path.basename(filepath)

                # 跳过明显不是DICOM的文件
                non_dicom_extensions = [
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
                    ".avi",
                    ".mp4",
                    ".mov",
                    ".mkv",
                    ".wmv",
                    ".html",
                    ".htm",
                    ".xml",
                    ".json",
                    ".csv",
                ]

                for ext in non_dicom_extensions:
                    if filename.lower().endswith(ext):
                        return False

                # 对于其他文件，检查文件大小范围
                # 典型的DICOM文件大小在几十KB到几百MB之间
                if (
                    file_size < 1024 or file_size > 2 * 1024 * 1024 * 1024
                ):  # 小于1KB或大于2GB
                    return False

                # 方法4：作为最后手段，尝试pydicom解析
                try:
                    pydicom.dcmread(filepath, stop_before_pixels=True, force=True)
                    return True
                except (InvalidDicomError, Exception):
                    return False

            except Exception:
                return False

        # ===========================================

        if self.keep_original.get():
            dst_root = src_root + "_anon"
            if os.path.exists(dst_root):
                try:
                    shutil.rmtree(dst_root)
                except Exception as e:
                    self.ui_queue.put(
                        ("log", f"Warning: Could not clear {dst_root}: {e}")
                    )
            os.makedirs(dst_root, exist_ok=True)
        else:
            dst_root = src_root

        # ================= 自动判断病例目录 =================

        # ================= 自动判断病例目录 =================

        if self.modality.get() in ["MRI", "CT"]:
            # 对于MRI和CT，我们需要检测病例目录
            # 病例目录的定义：包含DICOM文件的目录
            cases = []

            # 方法1：先找直接包含DICOM文件的子目录
            for item in os.listdir(src_root):
                item_path = os.path.join(src_root, item)
                if os.path.isdir(item_path):
                    # 检查这个目录是否包含DICOM文件
                    dicom_found = False
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            filepath = os.path.join(root, file)
                            if is_dicom_quick(filepath):
                                cases.append(item)
                                dicom_found = True
                                break
                        if dicom_found:
                            break

            # 方法2：如果没找到子目录包含DICOM，检查src_root本身
            if not cases:
                self.ui_queue.put(
                    (
                        "log",
                        "No subdirectories with DICOM found, checking root directory...",
                    )
                )

                root_has_dicom = False
                for root, dirs, files in os.walk(src_root):
                    for file in files:
                        filepath = os.path.join(root, file)
                        if is_dicom_quick(filepath):
                            root_has_dicom = True
                            break
                    if root_has_dicom:
                        break

                if root_has_dicom:
                    # 如果src_root包含DICOM，将其作为单个病例
                    cases = [""]  # 空字符串表示根目录本身
                    self.ui_queue.put(
                        (
                            "log",
                            "Root directory contains DICOM files, treating as single case",
                        )
                    )

            if not cases:
                self.ui_queue.put(
                    ("status", "No DICOM files found in input directory", "red")
                )
                self.ui_queue.put(("done", None))
                self._schedule_ui_queue()
                return

            self.ui_queue.put(
                (
                    "log",
                    f"Found {len(cases)} case directories with DICOM files",
                )
            )
            self.ui_queue.put(("log", f"Case list: {cases}"))

        else:
            # 使用现有的逻辑（用于超声DICOM和视频）
            cases = []
            for root, dirs, files in os.walk(src_root):
                # 检查这个目录是否有可处理文件
                has_dicom = any(f.lower().endswith(".dcm") for f in files)
                has_avi = any(f.lower().endswith(".avi") for f in files)

                if has_dicom or has_avi:
                    # 保存相对路径，保持目录结构
                    rel_path = os.path.relpath(root, src_root)
                    cases.append(rel_path)

            if not cases:
                self.ui_queue.put(
                    ("status", "No valid cases found in input directory", "red")
                )
                self.ui_queue.put(("done", None))
                self._schedule_ui_queue()
                return

        total_cases = len(cases)
        self.ui_queue.put(("log", f"Found {total_cases} case directories"))
        self._schedule_ui_queue()

        processed_cases = 0
        total_files_processed = 0

        for i, case in enumerate(cases, 1):
            if self.stop_requested:
                self.ui_queue.put(("log", "Batch processing stopped by user"))
                percent = (
                    int(processed_cases / total_cases * 100) if total_cases > 0 else 0
                )
                self.ui_queue.put(
                    ("progress", percent, f"Stopped ({processed_cases}/{total_cases})")
                )
                break

            # 在循环开始时定义 display_case
            if case == "":  # 空字符串表示根目录
                display_case = "[Root Directory]"
            else:
                display_case = case

            self.ui_queue.put(
                ("status", f"Processing: {display_case} ({i}/{total_cases})", "black")
            )
            self._schedule_ui_queue()

            try:
                # 处理根目录的情况
                if case == "":  # 空字符串表示根目录
                    src_case = src_root
                else:
                    src_case = os.path.join(src_root, case)

                if not os.path.isdir(src_case):
                    self.ui_queue.put(("log", f"Skipping non-directory: {case}"))
                    continue

                if self.keep_original.get():
                    dst_case = os.path.join(dst_root, case)

                    if self.modality.get() in ["MRI", "CT"]:
                        # CT/MRI需要完整复制目录树
                        try:
                            # 删除已存在的目标目录
                            if os.path.exists(dst_case):
                                shutil.rmtree(dst_case)

                            # 使用copytree完整复制
                            shutil.copytree(src_case, dst_case)

                            # 验证复制
                            src_items = os.listdir(src_case)
                            dst_items = os.listdir(dst_case)
                            missing = [
                                item for item in src_items if item not in dst_items
                            ]

                            if missing:
                                self.ui_queue.put(
                                    ("log", f"⚠️ 复制可能不完整，缺失: {missing}")
                                )
                            else:
                                self.ui_queue.put(
                                    ("log", f"✓ 完整复制CT/MRI病例: {display_case}")
                                )

                        except Exception as e:
                            self.ui_queue.put(
                                ("log", f"❌ 复制CT/MRI失败 {display_case}: {str(e)}")
                            )
                            continue
                    else:
                        # 超声DICOM/视频使用原来的文件复制
                        os.makedirs(dst_case, exist_ok=True)
                        for f in os.listdir(src_case):
                            src_file = os.path.join(src_case, f)
                            dst_file = os.path.join(dst_case, f)
                            if os.path.isfile(src_file):
                                shutil.copy2(src_file, dst_file)
                        self.ui_queue.put(
                            ("log", f"Copied {display_case or '.'} to destination")
                        )
                    # ============ End ============

                else:
                    dst_case = src_case

                case_files_processed = 0

                if self.modality.get() == "MRI":
                    case_files_processed = anonymize_mri_case(
                        dst_case,
                        log=lambda m: self.ui_queue.put(("log", m)),
                    )
                    if hasattr(self, "jpeg_mask_cfg") and self.jpeg_mask_cfg.get(
                        "regions"
                    ):
                        jpeg_files_processed = self.process_jpeg_files(dst_case)
                        case_files_processed += jpeg_files_processed
                        self.ui_queue.put(
                            ("log", f"→ Processed {jpeg_files_processed} JPEG files")
                        )

                elif self.modality.get() == "CT":
                    case_files_processed = anonymize_ct_case(
                        dst_case,
                        log=lambda m: self.ui_queue.put(("log", m)),
                    )
                    if hasattr(self, "jpeg_mask_cfg") and self.jpeg_mask_cfg.get(
                        "regions"
                    ):
                        jpeg_files_processed = self.process_jpeg_files(dst_case)
                        case_files_processed += jpeg_files_processed
                        self.ui_queue.put(
                            ("log", f"→ Processed {jpeg_files_processed} JPEG files")
                        )

                elif self.modality.get() == "Ultrasound DICOM":  # Ultrasound DICOM
                    case_files_processed = anonymize_ultrasound_dicom_complete(
                        dst_case,
                        log=lambda m: self.ui_queue.put(("log", m)),
                    )

                else:  # ICE 或 TTE
                    avi_files = []
                    for r, _, fs in os.walk(dst_case):
                        for f in fs:
                            if f.lower().endswith(".avi"):
                                avi_files.append(os.path.join(r, f))

                    if not avi_files:
                        self.ui_queue.put(("log", f"No AVI files found in {case}"))
                    else:
                        self.ui_queue.put(
                            ("log", f"Found {len(avi_files)} AVI files in {case}")
                        )

                    for avi_file in avi_files:
                        if self.stop_requested:
                            break

                        file_name = os.path.basename(avi_file)
                        self.ui_queue.put(("log", f"Processing: {file_name}"))
                        self._schedule_ui_queue()

                        try:
                            # 使用临时文件
                            temp_file = avi_file + ".temp.avi"

                            # 处理视频
                            frame_count = anonymize_video(
                                avi_file,
                                temp_file,
                                self.video_mask_cfg["direction"],
                                self.video_mask_cfg["size"],
                                modality=self.modality.get(),
                            )

                            # 替换原文件
                            if os.path.exists(temp_file):
                                if not self.keep_original.get():
                                    backup_file = avi_file + ".backup"
                                    shutil.copy2(avi_file, backup_file)

                                os.remove(avi_file)
                                shutil.move(temp_file, avi_file)

                                case_files_processed += 1
                                total_files_processed += 1

                                self.ui_queue.put(
                                    (
                                        "log",
                                        f"  ✓ Successfully processed {frame_count} frames",
                                    )
                                )

                        except Exception as e:
                            self.ui_queue.put(
                                ("log", f"  ❌ Error processing {file_name}: {str(e)}")
                            )
                            if os.path.exists(avi_file + ".temp.avi"):
                                try:
                                    os.remove(avi_file + ".temp.avi")
                                except:
                                    pass
                            continue

                processed_cases += 1
                total_files_processed += case_files_processed
                percent = (
                    int(processed_cases / total_cases * 100) if total_cases > 0 else 0
                )

                self.ui_queue.put(
                    (
                        "progress",
                        percent,  # ✅ 更新实际完成的百分比
                        f"Completed: {display_case} ({processed_cases}/{total_cases})",
                    )
                )
                self.ui_queue.put(
                    (
                        "log",
                        f"→ Processed {case_files_processed} {self.modality.get()} files in {display_case}",
                    )
                )
                self._schedule_ui_queue()

            except Exception as e:
                processed_cases += 1
                percent = (
                    int(processed_cases / total_cases * 100) if total_cases > 0 else 0
                )

                self.ui_queue.put(("log", f"❌ Error processing case {case}: {str(e)}"))
                self.ui_queue.put(
                    (
                        "progress",
                        percent,
                        f"Failed: {display_case} ({processed_cases}/{total_cases})",
                    )
                )
                import traceback

                self.ui_queue.put(("log", f"Traceback: {traceback.format_exc()}"))
                self._schedule_ui_queue()  # ✅ 确保异常情况下也更新UI

        # ✅ 所有case处理完成后
        self.ui_queue.put(("log", f"\n=== Batch Processing Complete ==="))
        self.ui_queue.put(
            ("log", f"Total cases processed: {processed_cases}/{total_cases}")
        )
        self.ui_queue.put(("log", f"Total files processed: {total_files_processed}"))
        self.ui_queue.put(("log", f"Output directory: {dst_root}"))

        # ✅ 确保最终进度是100%
        if not self.stop_requested:
            self.ui_queue.put(("progress", 100, "All cases completed"))

        self.ui_queue.put(("done", None))
        self._schedule_ui_queue()

    def _on_batch_finished(self):
        self.progress["value"] = 100
        self.progress_label.config(text="Done")
        self.current_case_label.config(text="All cases processed")
        self.status_label.config(
            text="Batch anonymization completed",
            foreground="green",
        )
        self.exit_btn.config(state="normal")

    def on_exit(self):
        self.root.quit()
        self.root.destroy()


def show_info_dialog(parent):
    dialog = tk.Toplevel(parent)
    dialog.title("Batch Medical Data Desensitization")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    w, h = 420, 260
    parent.update_idletasks()
    x = parent.winfo_screenwidth() // 2 - w // 2
    y = parent.winfo_screenheight() // 2 - h // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    ttk.Label(
        dialog,
        text=(
            "功能：批量处理 MRI/CT/ICE/TTE/DICOM 医疗数据除敏\n\n"
            "设计人：Zhuheng Li\n\n"
            "使用前请同意以下条款：\n"
            "1. 本软件仅供内部使用\n"
            "2. 处理数据请遵守隐私法规\n"
            "3. 使用本软件风险自负"
        ),
        justify="left",
        padding=15,
    ).pack(fill="both", expand=True)

    agreed = {"ok": False}

    def on_ok():
        agreed["ok"] = True
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    btns = ttk.Frame(dialog)
    btns.pack(pady=10)
    ttk.Button(btns, text="OK", command=on_ok).pack(side="left", padx=8)
    ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="left", padx=8)

    parent.wait_window(dialog)
    return agreed["ok"]


def safe_imread(path, flags=cv2.IMREAD_COLOR):
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)

def safe_imwrite(path, img):
    ext = os.path.splitext(path)[1]
    success, encoded = cv2.imencode(ext, img)
    if not success:
        raise RuntimeError("imencode failed")
    encoded.tofile(path)


if __name__ == "__main__":
    root = tk.Tk()

    root.geometry("1x1+0+0")
    root.attributes("-alpha", 0.0)
    root.update_idletasks()

    if not show_info_dialog(root):
        root.destroy()
        sys.exit(0)

    root.attributes("-alpha", 1.0)
    root.deiconify()
    root.lift()
    root.focus_force()

    app = BatchAnonymizationApp(root)
    root.after_idle(lambda: app.browse_btn.focus_set())
    root.mainloop()
