import os
import sys
import threading
import subprocess
import traceback
import multiprocessing
from multiprocessing import Pool, cpu_count, Manager, freeze_support

from tkinter import Tk, Label, Button, filedialog, Entry, messagebox, Frame, StringVar, DISABLED, NORMAL, Checkbutton, IntVar
from tkinter.ttk import Progressbar, Style
from PIL import Image

SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.ppm', '.pgm', '.webp', '.ico', '.im', '.pcx', '.sgi', '.tga', '.xbm', '.psd')


def compress_single_image(input_image_path, output_image_path, target_size_kb, progress_queue, cancel_flag):
    if cancel_flag.value:
        return
    try:
        input_image_path = os.path.normpath(input_image_path)
        output_image_path = os.path.normpath(output_image_path)
        os.makedirs(os.path.split(output_image_path)[0], exist_ok=True)
        file_size_kb = os.path.getsize(input_image_path) / 1024
        gap = 0  # 控制误差范围

        with Image.open(input_image_path) as img:
            scale_factor = 1.0
            iteration = 0
            while iteration < 20:
                if cancel_flag.value:
                    return
                new_width = int(img.width * scale_factor)
                new_height = int(img.height * scale_factor)
                img_resized = img.resize((new_width, new_height), Image.LANCZOS)
                img_resized.convert('RGB').save(output_image_path, 'JPEG', quality=95)
                output_size_kb = os.path.getsize(output_image_path) / 1024
                if output_size_kb < float(target_size_kb) + gap:
                    break
                ratio = output_size_kb / float(target_size_kb)
                if ratio > 10:
                    scale_factor *= 0.5
                elif ratio > 5:
                    scale_factor *= 0.6
                elif ratio > 3:
                    scale_factor *= 0.7
                elif ratio > 2:
                    scale_factor *= 0.8
                elif ratio > 1.1:
                    scale_factor *= 0.9
                else:
                    scale_factor *= 0.95
                iteration += 1

            if output_size_kb > float(target_size_kb) + gap:
                quality = 95
                while output_size_kb > float(target_size_kb) + gap and quality > 10:
                    if cancel_flag.value:
                        return
                    quality -= 1
                    img_resized.convert('RGB').save(output_image_path, 'JPEG', quality=quality)
                    output_size_kb = os.path.getsize(output_image_path) / 1024

            print(f"压缩完大小：{output_size_kb}, 原图大小：{file_size_kb}, {input_image_path}")
    except:
        print(f'Error compressing image: {input_image_path}, error_msg={traceback.format_exc()}')
    finally:
        if progress_queue is not None:
            progress_queue.put(1)


def get_all_image_files(input_folder):
    image_files = []
    for root, dirs, files in os.walk(input_folder):
        for file in files:
            if file.lower().endswith(SUPPORTED_FORMATS):
                image_files.append(os.path.join(root, file))
    return image_files


def compress_images(input_folder, output_folder, target_size_kb, progress_callback, cancel_flag, use_multiprocessing):
    files = get_all_image_files(input_folder)
    total_files = len(files)
    
    if use_multiprocessing:
        manager = Manager()
        progress_queue = manager.Queue()
        pool_args = [
            (
                input_image_path,
                os.path.join(output_folder, os.path.relpath(os.path.splitext(input_image_path)[0], input_folder) + '.jpg'),
                target_size_kb,
                progress_queue,
                cancel_flag
            )
            for input_image_path in files
        ]
        num_processes = max(1, cpu_count() // 2)
        
        with Pool(processes=num_processes) as pool:
            for args in pool_args:
                pool.apply_async(compress_single_image, args=args)
            
            pool.close()
            
            processed_files = 0
            while processed_files < total_files:
                try:
                    progress_queue.get(timeout=0.1)  # Adding timeout to avoid blocking indefinitely
                    processed_files += 1
                    progress_callback(processed_files, total_files)
                except:
                    if cancel_flag.value:
                        break
            
            pool.terminate()
    else:
        for i, input_image_path in enumerate(files):
            if cancel_flag.value:
                break
            output_image_path = os.path.join(output_folder, os.path.relpath(os.path.splitext(input_image_path)[0], input_folder) + '.jpg')
            compress_single_image(input_image_path, output_image_path, target_size_kb, None, cancel_flag)
            progress_callback(i + 1, total_files)
    
    if not cancel_flag.value:
        messagebox.showinfo("完成", f"所有图片处理完毕，有效压缩图片{total_files}张！")
    
    clear_progress()
    enable_controls()


def update_progress(current, total):
    progress['value'] = (current / total) * 100
    progress_var.set(f"{int((current / total) * 100)}%")
    root.update_idletasks()


def clear_progress():
    progress['value'] = 0
    progress_var.set("")
    progress.grid_remove()
    progress_label.grid_remove()


def select_folder(label, default_text):
    folder_path = filedialog.askdirectory()
    if folder_path:
        label.config(text=folder_path)
    else:
        label.config(text=default_text)
    return folder_path


def start_compress_thread(input_folder, output_folder, target_size_kb, progress_callback):
    global cancel_flag
    if not input_folder or input_folder == "选择输入文件夹:":
        messagebox.showwarning("警告", "请选择输入文件夹")
        return
    if not output_folder or output_folder == "选择输出文件夹:":
        messagebox.showwarning("警告", "请选择输出文件夹")
        return
    if output_folder == input_folder:
        messagebox.showwarning("警告", "输入和输出不能是同一个文件夹")
        return
    progress.grid(row=4, column=0, columnspan=2, pady=10, sticky='we')
    progress_label.grid(row=4, column=2, sticky='w')
    cancel_button.grid(row=5, column=0, columnspan=3, pady=10)
    disable_controls()
    
    manager = Manager()
    cancel_flag = manager.Value('i', 0)
    use_multiprocessing = bool(use_accelerator.get())
    threading.Thread(target=compress_images, args=(input_folder, output_folder, target_size_kb, progress_callback, cancel_flag, use_multiprocessing)).start()
    cancel_button.config(command=lambda: cancel_compress())


def open_output_folder(folder_path):
    if os.path.exists(folder_path):
        if os.name == 'nt':  # Windows
            subprocess.run(['explorer', folder_path])


def cancel_compress():
    global cancel_flag
    result = messagebox.askyesno("确认取消", "确定要取消图片压缩吗？")
    if result:
        cancel_flag.value = 1


def disable_controls():
    btn_input.config(state=DISABLED)
    btn_output.config(state=DISABLED)
    target_size_kb_entry.config(state=DISABLED)
    btn_compress.config(state=DISABLED)
    cancel_button.config(state=NORMAL)


def enable_controls():
    btn_input.config(state=NORMAL)
    btn_output.config(state=NORMAL)
    target_size_kb_entry.config(state=NORMAL)
    btn_compress.config(state=NORMAL)
    cancel_button.grid_remove()


def get_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.normpath(os.path.join(base_path, relative_path))


def main():
    global root, progress, progress_var, progress_label, target_size_kb_entry, btn_input, btn_output, btn_compress, cancel_button, use_accelerator
    root = Tk()
    root.title("想怎么压就怎么压！")
    root.configure(bg='#2e2e2e')
    root.iconbitmap(get_path('logo.ico'))

    style = Style()
    style.theme_use('clam')
    style.configure('TButton', font=('Helvetica', 12, 'bold'), foreground='white', background='#4d4d4d', anchor='w')
    style.configure('TLabel', font=('Helvetica', 12), background='#2e2e2e', foreground='white', anchor='w')
    style.configure('TEntry', font=('Helvetica', 12), fieldbackground='#2e2e2e', foreground='white')
    style.configure('Horizontal.TProgressbar', troughcolor='#4d4d4d', background='white', thickness=20)

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = screen_width // 2
    window_height = screen_height // 2
    window_x = (screen_width - window_width) // 2
    window_y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")

    title_label = Label(root, text="~ 图片压缩统统hold住 ~", font=('Helvetica', 16, 'bold'), bg='#2e2e2e', fg='white')
    title_label.pack(pady=10)

    frame = Frame(root, relief='groove', borderwidth=3, padx=30, pady=20, bg='#2e2e2e')
    frame.place(relx=0.5, rely=0.5, anchor='center')

    lbl_input_default_text = "选择输入文件夹:"
    lbl_input = Label(frame, text=lbl_input_default_text, bg='#2e2e2e', fg='white')
    lbl_input.grid(row=0, column=0, sticky='w', pady=8)
    btn_input = Button(frame, text="浏览", command=lambda: select_folder(lbl_input, lbl_input_default_text), bg='#4d4d4d', fg='white')
    btn_input.grid(row=0, column=1, padx=4, pady=8)

    lbl_output_default_text = "选择输出文件夹:"
    lbl_output = Label(frame, text=lbl_output_default_text, bg='#2e2e2e', fg='white')
    lbl_output.grid(row=1, column=0, sticky='w', pady=8)
    btn_output = Button(frame, text="浏览", command=lambda: select_folder(lbl_output, lbl_output_default_text), bg='#4d4d4d', fg='white')
    btn_output.grid(row=1, column=1, padx=4, pady=8)

    lbl_target_size = Label(frame, text="图片大小不超过:", bg='#2e2e2e', fg='white')
    lbl_target_size.grid(row=2, column=0, sticky='e', pady=8)
    target_size_kb_entry = Entry(frame, width=4, bg='#2e2e2e', fg='white')
    target_size_kb_entry.grid(row=2, column=1, sticky='w', pady=8, padx=20)
    target_size_kb_entry.insert(0, "500")
    lbl_target_unit = Label(frame, text="KB", bg='#2e2e2e', fg='white')
    lbl_target_unit.grid(row=2, column=2, sticky='w', pady=8)

    use_accelerator = IntVar()
    accelerator_label = Label(frame, text="是否开启加速器:", bg='#2e2e2e', fg='white')
    accelerator_label.grid(row=3, column=0, sticky='e', pady=8)
    accelerator_check = Checkbutton(frame, variable=use_accelerator, bg='#2e2e2e', fg='white', selectcolor='#4d4d4d')
    accelerator_check.grid(row=3, column=1, sticky='w', pady=8, padx=15)

    progress_var = StringVar()
    progress = Progressbar(frame, orient='horizontal', length=200, mode='determinate', style='Horizontal.TProgressbar')
    progress_label = Label(frame, textvariable=progress_var, bg='#2e2e2e', fg='white')

    btn_compress = Button(
        frame,
        text="开始压缩",
        command=lambda: start_compress_thread(
            lbl_input.cget("text"),
            lbl_output.cget("text"),
            target_size_kb_entry.get(),
            update_progress
        ),
        bg='#4d4d4d',
        fg='white'
    )
    btn_compress.grid(row=5, column=0, columnspan=3, pady=10)

    cancel_button = Button(frame, text="取消压缩", command=cancel_compress, state=DISABLED, bg='#4d4d4d', fg='white')
    cancel_button.grid(row=6, column=0, columnspan=3, pady=10)
    cancel_button.grid_remove()

    root.mainloop()


if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')
    freeze_support()  # For Windows support
    main()

    # pyinstaller.exe -F --windowed --icon=logo.ico --add-data "logo.ico;." compress_image.py
