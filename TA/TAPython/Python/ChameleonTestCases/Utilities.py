import logging
import os
import time

import unreal
from pprint import pprint
# from PIL import Image
# import keras_ocr


def py_task(func, *args, **kwargs):
    qualname = func.__qualname__
    arg_str = ""
    if args:
        arg_str = str(args)[1:-1]
    if kwargs:
        if arg_str:
            arg_str += ", "
        arg_str += ", ".join(f'{k}="{v}"' if isinstance(v, str) else f'{k}={v}' for k, v in kwargs.items())

    if func.__module__:
        class_name, function_name = qualname.split(".")
        cmd_get_instance =f"{func.__module__}.{class_name}.get_instance_name()"

        result = unreal.PythonScriptLibrary.execute_python_command_ex(cmd_get_instance
                                                  , unreal.PythonCommandExecutionMode.EXECUTE_STATEMENT
                                                  , file_execution_scope=unreal.PythonFileExecutionScope.PUBLIC)

        instance_name = ""
        if result:
            for x in result[1]:
                if x.output:
                    instance_name = x.output[1:-1]
                break
        assert instance_name, f"instance_name: {instance_name}"
        cmd = f"{instance_name}.{function_name}({arg_str})"
    else:
        cmd = f"unreal.{qualname}({arg_str})"   # ue blueprint callable 的module 为空
    print(f"py_task: {cmd}")
    return cmd


bOcr = True
ocr_reader = None
try:
    import easyocr
except Exception as e :
    unreal.log_error("No module easyocr. Ocr disalbed")
    bOcr = False


def editor_delay_call(py_cmd, delay_seconds):
    unreal.PythonTestLib.push_call(py_cmd, delay_seconds)


def editor_snapshot(window_name):
    if window_name is None:
        print("\tTake editor shot")
        unreal.PythonBPLib.execute_console_command(f"EditorShot")
    else:
        print(f'\tEditorShot Name="{window_name}"')
        unreal.PythonBPLib.execute_console_command(f'EditorShot Name="{window_name}"')


def get_latest_snaps(time_from_now_limit:float, group_threshold:float) -> [str]:
    result = []
    prject_folder = unreal.SystemLibrary.get_project_directory()
    saved_folder = os.path.abspath(os.path.join(prject_folder, "Saved/Screenshots/WindowsEditor"))
    if not os.path.exists(saved_folder):
        unreal.log_error("Can't find Screenshots folder")

    file_paths = [os.path.join(saved_folder, file_name) for file_name in os.listdir(saved_folder)]
    if not file_paths:
        return result

    file_mtime = [os.path.getmtime(file_path) for file_path in file_paths]

    # print(f"file_paths: {file_paths}")
    # print(f"file_mtime: {file_mtime}")

    sorted_file_path = [x for _, x in sorted(zip(file_mtime, file_paths), reverse=True)]
    file_mtime = sorted(file_mtime, reverse=True)

    assert file_mtime[0] >= file_mtime[-1], "time need sorted"
    latest_time = file_mtime[0]

    now = time.time()
    for i, t in enumerate(file_mtime):
        if time_from_now_limit > 0 and t < now - time_from_now_limit:
            break
        if latest_time - t < group_threshold:
            result.append(sorted_file_path[i])
    return result


def get_ocr_reader():
    global ocr_reader
    if bOcr:
        ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return ocr_reader



def get_ocr_from_file(file_path:str):
    if not os.path.exists(file_path):
        unreal.log_warning(f"Error: file: snap file: {file_path} not exists")
    else:
        if bOcr:
            return get_ocr_reader().readtext(file_path)
    return None

def assert_ocr_text(file_path:str, target_str:str, bStrict) -> str:
    succ = "PASS"
    if not bOcr:
        return f"Warning: can't find easyocr"
    if not file_path:
        unreal.log_warning(f"snapfile_path None: {file_path}")
        return f"Error: snapfile_path None"
    if not os.path.exists(file_path):
        return f"Error: file: snap file: {file_path} not exists"
    try:
        r = get_ocr_reader().readtext(file_path)

        if bStrict:
            if len(r) == 1 and target_str == r[0][1]:
                return succ
        else:
            for x in r:
                if len(x) > 1 and target_str in x[1]:
                    return succ

    except Exception as e:
        str_e = str(e)
        unreal.log_error(str_e)
        return str_e
    unreal.log_warning(f"\t Assert_ocr_text Failed target_str: {target_str} result: {r} @ {file_path}")
    return "Failed"


def get_esp_time_from_log(log, current_time):
    pass


def assert_log(log_str, bNoError, bClear=False):
    logs = unreal.PythonBPLib.get_logs()

    for i in range(len(logs) - 1, -1, -1):
        log = logs[i]

    if bClear:
        unreal.PythonBPLib.clear_log_buffer()


if __name__ == "__main__":
    print("main")
    folder = r"D:\UnrealProjects\5_0\TAPython_TestCase\Saved\Screenshots\WindowsEditor"
    file_path = os.path.join(folder, "EditorScreenshot00000.bmp")
    reader = easyocr.Reader(['en', 'ch_sim'])
    r = reader.readtext(file_path)
    # images = [keras_ocr.tools.read(file_path)]
    # pipeline = keras_ocr.pipeline.Pipeline()
    # r = pipeline.recognizer(images)
    print(r)
    print("done")
