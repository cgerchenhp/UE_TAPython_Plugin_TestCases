import math
import os
import re
import inspect
import struct
import json
from typing import List

from Utilities.Utils import EObjectFlags

from .Utilities import get_latest_snaps, editor_snapshot, assert_ocr_text, py_task
from .Utilities import get_ocr_from_file


import unreal
from Utilities.Utils import Singleton

class TestPythonAPIs(metaclass=Singleton):
    def __init__(self, jsonPath:str):
        self.jsonPath = jsonPath
        self.data = unreal.PythonBPLib.get_chameleon_data(self.jsonPath)

        self.latest_snaps = None
        self.ui_output = "Output"
        self.ui_logs = "OutputLog"

        self.current_task_id = -1
        self.current_task_sum = -1
        self.test_results = []
        self.temp_assets_folder = "/Game/_AssetsForTAPythonTestCase"
        self.temp_asset = None
        self.output_logs = ""

    @staticmethod
    def get_instance_name():
        return "chameleon_general_test" # shoule equal with instance name in JSON

    def get_color_from_result_str(self, result_str:str):
        lower_str = result_str.lower()
        bPass = "pass" in lower_str
        bFailed = "error" in lower_str or "failed" in lower_str

        if bFailed:
            if bPass:
                return unreal.LinearColor(1, 0.5, 0, 1) # part
            else:
                return unreal.LinearColor.RED
        else:
            if bPass:
                return unreal.LinearColor.GREEN
        return unreal.LinearColor.WHITE

    def add_log(self, log_str, level=0):
        unreal.log(log_str)
        if self.output_logs:
            self.output_logs += "\n"
        if level == 0:
            self.output_logs += log_str
        elif level == 1:
            self.output_logs += "<RichText.orange>{}</>".format(log_str)
        elif level == 2:
            self.output_logs += "<RichText.red>{}</>".format(log_str)
        elif level == -1:
            self.output_logs += "<RichText.green>{}</>".format(log_str)
        else:
            assert False
        self.data.set_text(self.ui_logs, self.output_logs)
        self.data.scroll_to(self.ui_logs, -1)

    def clear_output_logs(self):
        self.output_logs = ""
        self.data.set_text(self.ui_logs, self.output_logs)

    # ----------------------------------------------------------------------------------------------------------------
    def task_notification_snapshot(self):
        editor_snapshot(window_name="")

    def check_notification_result(self, target_str, bStrict, time_from_now_limit=1):
        succ, msg = False, ""
        try:
            self.latest_snaps = get_latest_snaps(time_from_now_limit=time_from_now_limit, group_threshold=1)
            if len(self.latest_snaps) > 1:
                for i, path in enumerate(self.latest_snaps):
                    print(f"\t\tmulti snap files {i}: {os.path.basename(path)}, t: {os.path.getmtime(path)}")

            snap_image = self.latest_snaps[0] if len(self.latest_snaps) > 0 else None
            if not snap_image:
                unreal.log_warning(f"Can't find snap image: {snap_image}")
            msg = assert_ocr_text(snap_image, target_str, bStrict=bStrict)
            succ = True
        except Exception as e:
            msg = str(e)
        # self.test_results.append(result)
        # self.set_test_result(" | ".join(self.test_results), 0)
        self.push_result(succ, msg)

    def check_latest_snap(self, assert_count=-1, assert_strings=[]):
        self.latest_snaps = get_latest_snaps(time_from_now_limit=-1, group_threshold=1)
        snap_image = self.latest_snaps[0] if len(self.latest_snaps) > 0 else None
        error = []
        if snap_image:
            ocr_result = get_ocr_from_file(snap_image)
            if not ocr_result:
                error.append(f"No ocr module.")
            else:
                if assert_count != -1:
                    if len(ocr_result) != assert_count:
                        error.append(f"count not match: {assert_count} vs current: {len(ocr_result)}")
                if assert_strings:
                    for c, t in zip([v[1] for v in ocr_result], assert_strings):
                        if t == "*":
                            continue
                        if t not in c:
                            error.append(f"Can't find: \"{t}\" in ocr_result: \"{c}\"")

        if error:
            unreal.log_warning(f"Check Latest Snap Failed, ocr_result: ")
            if ocr_result:
                for x in ocr_result:
                    print(f"\t{x[1]}")
            else:
                print("\tNone. Need 3rd package: easyocr.")
            return "Failed"
        return "PASS"

    def assert_last_snap(self, assert_count=-1, assert_strings=list()):
        result = self.check_latest_snap(assert_count, assert_strings)
        self.test_results.append(result)
        self.set_test_result(" | ".join(self.test_results), self.current_task_id)


    def asset_log(self, number_limit, targets:[str], bMatchAny:bool) -> (bool, str):
        logs = unreal.PythonTestLib.get_logs(number_limit)
        for log in logs:
            if bMatchAny:
                for t in targets:
                    if t in log:
                        print(f"asset_log match: {t}")
                        return True, None
            else:
                raise NotImplemented
        unreal.log_warning(f"Can't find: {', '.join(targets)} in log")
        return False, f"Not match: {targets}"

    def error_log_count(self, number_limit):
        logs = unreal.PythonTestLib.get_logs(number_limit)
        error_logs = [log for log in logs if "Error: "in log]
        return len(error_logs)

    def check_error_in_log(self):
        error_count = self.error_log_count(number_limit=-1)
        bHasError = error_count > 0
        self.push_result(not bHasError, f"Has {error_count} Error in log" if bHasError else "No Error in log" )


    def set_test_result(self, result:str, id:int):
        aka_name = f"ResultBox_{id}"
        self.data.set_text(aka_name, result)
        self.data.set_color_and_opacity(aka_name, self.get_color_from_result_str(result))

    def set_output(self,  output_str):
        self.data.set_text(self.ui_output, output_str)


    def test_being(self, id:int):
        if self.current_task_id != -1:
            return False

        assert id >= 0
        self.current_task_id = id
        self.current_task_sum = 0
        self.test_results = []
        self.data.set_text(f"ResultBox_{id}", "-")
        unreal.PythonTestLib.clear_log_buffer()
        print("log buffer cleared")

        self.add_log(f"TEST CATEGORY {id} START  -->")
        return True


    def push_result(self, succ, msg=""):
        print("push_result call...")

        self.test_results.append("PASS" if succ else "FAILED")

        if len(self.test_results) > 6:
            passed_count = self.test_results.count("PASS")
            failed_count = self.test_results.count("FAILED")
            assert len(self.test_results) == passed_count + failed_count
            if failed_count:
                self.set_test_result("Pass x {}, Failed x {}".format(passed_count, failed_count), self.current_task_id)
            else:
                self.set_test_result("Pass x {}".format(passed_count), self.current_task_id)
        else:
            self.set_test_result(" | ".join(self.test_results), self.current_task_id)

        if msg:
            if isinstance(msg, list):
                msgs = msg
                for i, m in enumerate(msgs):
                    bLast = i == len(msgs) - 1
                    level = level=0 if succ or not bLast else 1
                    if "warning" in m.lower():
                        level = 1
                    self.add_log(f"\t\tTEST RESULT {i+1}/{len(msgs)}: {m}", level=level)
            else:
                self.add_log(f"\t\tTEST RESULT: {msg}", level=0 if succ and "warning" not in msg.lower() else 1)

        self.add_log("PASS" if succ else "FAILED", level=-1 if succ else 2) # -1 green, 2 red

    def push_call(self, py_cmd, delay_seconds:float):
        self.current_task_sum += delay_seconds
        time_from_zero = self.current_task_sum
        set_cmd = f"chameleon_general_test.set_output('process: {time_from_zero} / ' + str(round(chameleon_general_test.current_task_sum*10)/10) + '...')"

        unreal.PythonTestLib.delay_call(set_cmd, time_from_zero - delay_seconds)
        unreal.PythonTestLib.delay_call(py_cmd, time_from_zero)


    def test_end(self, id:int):
        logs = unreal.PythonTestLib.get_logs()
        for line in logs:
            if "] Error:" in line:
                self.add_log(line, level=2)
        assert id == self.current_task_id, f"id: {id} != self.current_task_id: {self.current_task_id}"

        self.set_output(f"Done. ID {id}")
        self.add_log(f"<-------------- TEST CATEGORY {id} FINISH\n\n", level=0)

        self.current_task_id = -1

    def test_finish(self, id):
        self.push_call(py_task(self.test_end, id=id), 0.1)

    def add_test_log(self, msg):
        self.add_log("\t> " + msg)

    #==============================  Test Case Start  ==============================

    def test_category_notification(self):
        category_id = 0
        bBusy = not self.test_being(id=category_id)
        if bBusy:
            self.add_log(f"--- SKIP TEST CATEGORY {id}, still running tests ---", level=1)

        log, warning, error = 0, 1, 2

        # case 1, Notification1
        label = 'This is a notification'
        self.push_call(py_task(unreal.PythonBPLib.notification, message=label, expire_duration=1.0, log_to_console=False), delay_seconds=0.1)
        self.push_call(py_task(self.add_test_log, msg="PythonBPLib.notification"),delay_seconds=0.01)
        self.push_call(py_task(self.task_notification_snapshot), 1)
        self.push_call(py_task(self.check_notification_result, target_str=label, bStrict=True), 0.2)

        # case 2, warning
        label = "This is a warning"
        self.push_call(py_task(unreal.PythonBPLib.notification, message=label, info_level=warning, log_to_console=False), delay_seconds=1)
        self.push_call(py_task(self.add_test_log, msg="PythonBPLib.notification warning"), delay_seconds=0.01)
        self.push_call(py_task(self.task_notification_snapshot), 1)
        self.push_call(py_task(self.check_notification_result, target_str=label, bStrict=True), 0.2)

        # case 3, Error
        label = "This is a Error message"
        self.push_call(py_task(unreal.PythonBPLib.notification, message=label, info_level=error, log_to_console=False), delay_seconds=1)
        self.push_call(py_task(self.add_test_log, msg="PythonBPLib.notification error"), delay_seconds=0.01)
        self.push_call(py_task(self.task_notification_snapshot), 1)
        self.push_call(py_task(self.check_notification_result, target_str=label, bStrict=True), 0.2)

        # case 4, hyperlink
        label = "This is a message with hyper link"  # ocr may break the label into 2 or more strings.
        self.push_call(py_task( unreal.PythonBPLib.notification, message=label, log_to_console=False, hyperlink_text="TAPython", on_hyperlink_click_command="print('link clicked.')"), delay_seconds=1)
        self.push_call(py_task(self.add_test_log, msg="PythonBPLib.notification with hyperlink"), delay_seconds=0.01)
        self.push_call(py_task(self.task_notification_snapshot), 1)
        self.push_call(py_task(self.assert_last_snap, assert_count=2, assert_strings=[label, "*"]), 0.2)

        self.test_finish(category_id)


    def check_log_by_str(self, logs_target:[str]):
        succ, msg = False, ""
        try:
            succ, msg = self.asset_log(-1, logs_target, bMatchAny=True)
        except Exception as e:
            msg = str(e)
        self.push_result(succ, msg)

    def _testcase_save_file_dialog(self, dialog_title:str, default_path:str, default_file:str, file_types:str):
        self.add_test_log("PythonBPLib.save_file_dialog")

        file_paths = unreal.PythonBPLib.save_file_dialog(dialog_title, default_path, default_file, file_types)

        if len(file_paths) > 0:
            file_path = os.path.abspath(file_paths[0])
            print("save_file_dialog: " + file_path) # for result
            with open(file_paths[0], 'w', encoding="UTF-8") as f:
                f.write("Test\n")


    def _testcase_open_file_dialog(self, dialog_title:str, default_path:str, default_file:str, file_types:str):
        self.add_test_log("PythonBPLib.open_file_dialog")

        selected_file_paths = unreal.PythonBPLib.open_file_dialog(dialog_title, default_path, default_file, file_types)
        if len(selected_file_paths) > 0:
            print(os.path.abspath(selected_file_paths[0]))
        else:
            print(selected_file_paths)

    def _testcase_open_directory_dialog(self, dialog_title: str, default_path: str):
        self.add_test_log("PythonBPLib.open_directory_dialog")

        selected_directory = unreal.PythonBPLib.open_directory_dialog(dialog_title, default_path)
        print(os.path.abspath(selected_directory)) # for result

    def _testcase_open_new_asset_path_dialog(self):
        succ, msgs = False, []
        try:
            default_path = "/Game/StarterContent/Blueprints/Assets/BP_SomeBP_File"
            self.add_test_log("open_new_asset_path_dialog")
            selected_path = unreal.PythonBPLib.open_new_asset_path_dialog(dialog_title="Save Asset To"
                                    , default_path=default_path, allow_read_only_folders=False)
            msgs.append(selected_path)

            assert selected_path == default_path, f"open_new_asset_path_dialog result: {selected_path} != {default_path}"
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_open_pick_path_dialog(self):
        succ, msgs = False, []
        try:
            default_path = "/Game/StarterContent/Blueprints/Assets/" # default_path need endwith "/"
            self.add_test_log("open_pick_path_dialog")
            selected_path = unreal.PythonBPLib.open_pick_path_dialog(dialog_title="Pick a Folder"
                                                                          , default_path=default_path)
            msgs.append(selected_path)
            assert selected_path == default_path[:-1], f"open_new_asset_path_dialog result: {selected_path} != {default_path[:-1]}"
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)




    def test_category_dialogs(self):
        id = 1
        self.test_being(id=id)

        # 1
        message = "This is a Test Message, Click 'OK' to continue"
        title = "This is a test title"
        self.push_call(py_task(unreal.PythonBPLib.message_dialog, message=message, dialog_title=title), delay_seconds=0.1)
        log_result = f"Message dialog closed, result: Ok, title: {title}, text: {message}"
        self.push_call(py_task(self.add_test_log, msg="PythonBPLib.message_dialog"), delay_seconds=0.01)
        self.push_call(py_task(self.check_log_by_str, logs_target=[log_result]), delay_seconds=0.1)

        # 2
        message = "This is a Confirm Dialog, Click 'Yes' or 'No' to continue"
        title = "This is a Confirm Dialog"
        self.push_call(py_task(self.add_test_log, msg="PythonBPLib.confirm_dialog"), delay_seconds=0.01)
        self.push_call(py_task(unreal.PythonBPLib.confirm_dialog, message=message, dialog_title=title), delay_seconds=0.1)
        log_result = "dialog closed, result: Yes, title: This is a Confirm Dialog, text: This is a Confirm Dialog, Click 'Yes' or 'No' to continue"
        log_result1 = "dialog closed, result: No, title: This is a Confirm Dialog, text: This is a Confirm Dialog, Click 'Yes' or 'No' to continue"
        log_result2 = "dialog closed, result: Cancel, title: This is a Confirm Dialog, text: This is a Confirm Dialog, Click 'Yes' or 'No' to continue"
        targets = [log_result, log_result1, log_result2]
        self.push_call(py_task(self.check_log_by_str, logs_target=targets), delay_seconds=0.1)

        # 3 save file dialog
        dialog_title = "Save File Dialog"
        default_path = os.path.join(unreal.SystemLibrary.get_project_directory(), r"TA/TAPython/Python/ChameleonTestCases")
        assert os.path.exists(default_path), f"default path: {default_path} not exists."
        default_file = "test.txt"

        target_file_path = os.path.abspath(os.path.join(default_path, default_file))
        if not os.path.exists(target_file_path):
            with open(target_file_path, 'w') as f:
                pass

        file_types = "Text File (*.txt)|*.txt"
        self.push_call(py_task(self._testcase_save_file_dialog, dialog_title=dialog_title, default_path=default_path
                               , default_file=default_file, file_types=file_types), delay_seconds=0.1)
        self.push_call(py_task(self.check_log_by_str, logs_target=["save_file_dialog: " + target_file_path]), delay_seconds=0.5)

        # 4 open file dialog
        dialog_title = "Select test.txt"
        default_path = os.path.join(unreal.SystemLibrary.get_project_directory(), r"TA/TAPython/Python/ChameleonTestCases")
        assert os.path.exists(default_path), f"default path: {default_path} not exists."
        default_file = "test.txt"

        target_file_path = os.path.abspath(os.path.join(default_path, default_file))
        assert os.path.exists(target_file_path), f"path: {target_file_path} not exists."

        file_types = "Text File (*.txt)|*.txt"
        self.push_call(py_task(self._testcase_open_file_dialog, dialog_title=dialog_title, default_path=default_path
                               , default_file=default_file, file_types=file_types), delay_seconds=0.1)
        self.push_call(py_task(self.check_log_by_str, logs_target=[target_file_path]), delay_seconds=0.5)

        # 5
        dialog_title = "Directory Dialog"
        default_path = os.path.join(unreal.SystemLibrary.get_project_directory(), r"TA/TAPython/Python/ChameleonTestCases")
        self.push_call(py_task(self._testcase_open_directory_dialog, dialog_title=dialog_title, default_path=default_path), delay_seconds=0.1)
        target_file_path = os.path.abspath(default_path)
        self.push_call(py_task(self.check_log_by_str, logs_target=[target_file_path]), delay_seconds=0.1)

        # 6
        self.push_call(py_task(self._testcase_open_new_asset_path_dialog), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_open_pick_path_dialog), delay_seconds=0.1)

        self.test_finish(id)



    # -------------------------  Category 002 Info  -------------------------

    def _testcase_get_plugin_base_dir(self):
        self.add_test_log("get_plugin_base_dir")
        print(os.path.abspath(unreal.PythonBPLib.get_plugin_base_dir(plugin_name="TAPython")))

    def _testcase_get_engine_version(self):
        succ, msg = False, ""
        try:
            self.add_test_log("get_unreal_version")
            engine_version = unreal.PythonBPLib.get_unreal_version()
            if engine_version and isinstance(engine_version, unreal.Map):
                if len(engine_version) == 3:
                    version_str = f"{engine_version['major']}.{engine_version['Minor']}.{engine_version['Patch']}"
                    print(f"version_str: {version_str}")
                    succ = len(version_str) >=5  and version_str[0] == "4" or version_str[0] == "5"
            succ = True
        except Exception as e:
            msg = str(e)

        self.push_result(succ, msg)


    def _testcase_get_all_chameleon_data_paths(self):
        succ, msg = False, ""
        self.add_test_log("get_all_chameleon_data_paths")
        chameleon_paths = unreal.PythonBPLib.get_all_chameleon_data_paths()
        # chameleon path used for get the chamaleon tool's instance
        target_path = os.path.abspath(
            os.path.join(unreal.SystemLibrary.get_project_directory(), r"TA/TAPython/Python/ChameleonTestCases/TestPythonAPIs.json")
        )
        if len(chameleon_paths) > 0:
            for p in chameleon_paths:
                if os.path.abspath(p) == target_path:
                    succ = True
                    break
        if not succ:
            msg = ""
        self.push_result(succ, msg)

    def _testcase_clipboard(self):
        succ, msgs = False, []
        try:
            unreal.PythonBPLib.set_clipboard_content("abc")

            unreal.PythonBPLib.exec_python_command('print("~ {} ~".format(unreal.PythonBPLib.get_clipboard_content()))')
            logs = unreal.PythonTestLib.get_logs(1, "LogPython")
            assert logs and len(logs) == 1, f"logs: {logs} None or len != 1"
            assert logs[0].endswith("~ abc ~"), f"logs[0]: {logs[0]} content error."
            msgs.append("set_clipboard_content ok")
            msgs.append("get_clipboard_content ok")
            msgs.append("exec_python_command ok")
            succ = True
        except AssertionError as e:
            msgs.append(str(e))
        self.push_result(succ, msgs)

    def _testcase_get_viewport_content(self):
        succ, msgs = False, []
        pixels_and_size = unreal.PythonBPLib.get_viewport_pixels()
        try:
            assert pixels_and_size, "get_viewport_pixels failed. "
            assert len(pixels_and_size) ==2, f"pixels_and_size size failed"
            pixels, size = pixels_and_size
            assert pixels and size, "pixels or size None"
            assert len(pixels) == size.x * size.y, f"pixels count: {len(pixels)} == {size.x} * {size.y}"
            msgs.append("get_viewport_pixels ok")
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def test_category_get_infos(self, id:int):
        self.test_being(id=id)
        # 1
        self.push_call(py_task(self._testcase_get_plugin_base_dir), delay_seconds=0.1)
        target_log = os.path.abspath(os.path.join(unreal.SystemLibrary.get_project_directory(), r"Plugins/TAPython"))
        self.push_call(py_task(self.check_log_by_str, logs_target=[target_log]), delay_seconds=0.1)
        # 2
        self.push_call(py_task(self._testcase_get_engine_version), delay_seconds=0.1)
        # 3
        self.push_call(py_task(self._testcase_get_all_chameleon_data_paths), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_clipboard), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_get_viewport_content), delay_seconds=0.1)

        self.test_finish(id=id)

    # -------------------------  Category 003 actor  -------------------------

    def _testcase_get_all_worlds(self):
        self.add_test_log("get_all_worlds")
        for world in unreal.PythonBPLib.get_all_worlds():
            print(f"Test Result: {world.get_name()}")

    def get_editor_world(self):
        if unreal.PythonBPLib.get_unreal_version()["major"] == 5:
            return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        else:
            unreal.EditorLevelLibrary.get_editor_world()

    def _testcase_get_all_objects(self):
        # world = self.get_editor_world()

        world = unreal.EditorLevelLibrary.get_editor_world()
        assert world, "World None"
        self.add_test_log("get_all_objects")
        objects = unreal.PythonBPLib.get_all_objects(world, include_dead=False)
        succ, msg = False, ""
        all_types = set()
        if len(objects) > 50:
            for obj in objects:
                all_types.add(str(type(obj)))

        assert_types = {"<class 'ViewportStatsSubsystem'>", "<class 'BrushComponent'>", "<class 'WorldSettings'>"}
        succ = all_types & assert_types == assert_types
        if not succ:
            msg = unreal.log_warning(f"Asset types not all founded: {all_types & all_types}")
        self.push_result(succ, msg)

    def _testcase_get_objects_by_class(self):
        succ, msg = False, ""
        world = unreal.EditorLevelLibrary.get_editor_world()
        self.add_test_log("get_objects_by_class")
        objects = unreal.PythonBPLib.get_objects_by_class(world, unreal.InstancedFoliageActor)
        if len(objects) > 0 and objects[0].static_class().get_name() == "InstancedFoliageActor":
            succ = True
            msg = "found InstancedFoliageActor by class"
        self.push_result(succ, msg)


    def _testcase_get_actors_from_folder(self):
        succ, msg = False, ""
        try:
            self.add_test_log("get_actors_from_folder")
            objects_in_folder = unreal.PythonBPLib.get_actors_from_folder(unreal.EditorLevelLibrary.get_editor_world(), "Effects")
            object_names = {obj.get_name() for obj in objects_in_folder}
            assert_names = {"Blueprint_Effect_Fire_C_1", "Blueprint_Effect_Smoke_C_1"}
            succ = object_names & assert_names == assert_names
            msg = "{} effect object(s) in outliner's 'folder'".format(f"found {len(object_names)}" if succ else "Can't")
        except Exception as e:
            msg = str(e)
        self.push_result(succ, msg)



    def _testcase_find_actor(self):
        succ, msgs = False, []
        world = unreal.EditorLevelLibrary.get_editor_world()
        self.add_test_log("find_actor_by_name")
        actor_by_name = unreal.PythonBPLib.find_actor_by_name("SkyLight_6", world=world) #
        self.add_test_log("find_actors_by_label_name")
        actors_by_label = unreal.PythonBPLib.find_actors_by_label_name("SkyLight", world=world)
        try:
            # only one actor named SkyLight in level
            assert len(actors_by_label) == 1, f"len(actors_by_label): {len(actors_by_label)} != 1"
            assert actor_by_name == actors_by_label[0], f"actor_by_name != actors_by_label[0]. {actor_by_name} vs {actors_by_label[0]}"

            # multi actor named Chair
            actors_by_label = unreal.PythonBPLib.find_actors_by_label_name("PillarCorner", world=world)
            assert len(actors_by_label) > 1, f'"PillarCorner" actor number: {len(actors_by_label)} <= 1'
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_create_folder_in_outliner(self):
        succ, msgs = False, []
        world = unreal.EditorLevelLibrary.get_editor_world()
        actor_name = "SkyLight"
        actors_by_label = unreal.PythonBPLib.find_actors_by_label_name("SkyLight", world=world)
        if len(actors_by_label) == 0:
            msg = f"Can't find actor by label name: {actor_name}"
            self.push_result(succ, msg)
            return
        # 1 add folder
        outliner_folder_name = "AFolderForTestCase"
        unreal.PythonBPLib.create_folder_in_outliner(world, outliner_folder_name)

        # 2 assign
        actor = actors_by_label[0]
        unreal.PythonBPLib.select_none()
        unreal.PythonBPLib.select_actor(actor, selected=True, notify=True)
        unreal.PythonBPLib.set_selected_folder_path(outliner_folder_name)
        # 3 get
        actor_result = unreal.PythonBPLib.get_actors_from_folder(world, outliner_folder_name)
        try:
            assert actor in actor_result, f"actor: {actor} not in actor_result: len: {len(actor_result)}"
            succ = True
            msgs.append("Outliner folder ok")
        except AssertionError as e:
            succ = False
            msgs.append(str(e))

        # 4 rename
        new_outliner_folder_name = f"RenamedFolder/{outliner_folder_name}"  # nested folder in outliner
        unreal.PythonBPLib.rename_folder_in_world(world, outliner_folder_name, new_outliner_folder_name)
        actors_in_older_folder = unreal.PythonBPLib.get_actors_from_folder(world, outliner_folder_name)
        actors_in_new_folder = unreal.PythonBPLib.get_actors_from_folder(world, new_outliner_folder_name)
        try:
            assert not actors_in_older_folder, f"Actor still in older folder, count: {len(actors_in_older_folder)}"
            assert actor in actors_in_new_folder, f"actor: {actor} not in actors_in_new_folder: count: {len(actors_in_new_folder)}"
            msgs.append("Rename folder ok")
        except AssertionError as e:
            succ = False
            msgs.append(str(e))

        # delete
        unreal.PythonBPLib.delete_folder(world, "AnotherFolder")
        unreal.PythonBPLib.create_folder_in_outliner(world, "AnotherFolder")

        try:
            assert self.error_log_count(-1) == 0, "Has Error {}".format("\n".join(unreal.PythonTestLib.get_logs(-1)))
        except AssertionError as e:
            succ = False
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_world_composition(self):
        succ, msgs = False, []
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            objects = unreal.PythonBPLib.get_objects_by_class(world, unreal.WorldSettings)
            assert objects, "Can't find WorldSettings"
            world_settings = objects[0]
            current_v = world_settings.enable_world_composition
            assert not current_v, f"enable_world_composition: {current_v} != False"
            unreal.PythonBPLib.enable_world_composition(world, True)
            assert world_settings.enable_world_composition, "enable_world_composition != True"
            msgs.append("Set readonly world settings")

            unreal.PythonBPLib.enable_world_composition(world, False)
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_capture(self):
        succ, msg = False, ""
        self.add_test_log("update_reflection_capture_preview_shape")
        captures = unreal.PythonBPLib.get_objects_by_class(unreal.EditorLevelLibrary.get_editor_world(), unreal.SphereReflectionCapture)
        try:
            for capture in captures:
                unreal.PythonBPLib.update_reflection_capture_preview_shape(capture.get_editor_property("capture_component"))
            succ = True
        except Exception as e:
            msg = str(e)
        self.push_result(succ, msg)

    def test_category_level_actor(self, id:int):
        self.test_being(id=id)
        # 1
        level_path = '/Game/StarterContent/Maps/StarterMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_get_all_worlds), delay_seconds=0.5)
        self.push_call(py_task(self.check_log_by_str, logs_target=[f"Test Result: StarterMap"]), delay_seconds=0.1)
        # 2
        self.push_call(py_task(self._testcase_get_all_objects), delay_seconds=0.1)
        # # 3
        self.push_call(py_task(self._testcase_get_objects_by_class), delay_seconds=0.1)
        # 4
        self.push_call(py_task(self._testcase_get_actors_from_folder), delay_seconds=0.1)

        # 5 get object by name
        level_path = '/Game/StarterContent/Maps/StarterMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_find_actor), delay_seconds=0.1)

        # 6 prerequisite pass #5 _testcase_find_actor
        self.push_call(py_task(self._testcase_create_folder_in_outliner), delay_seconds=0.1)
        # 7 world composition
        level_path = '/Game/_AssetsForTAPythonTestCase/Maps/DefaultMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)

        level_path = '/Game/StarterContent/Maps/StarterMap'
        self.push_call(py_task(self._testcase_world_composition), delay_seconds=0.1)
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_capture), delay_seconds=0.1)


        self.test_finish(id=id)

    def _testcase_fov(self):
        succ, msg = True, ""
        self.add_test_log("get_level_viewport_camera_fov")
        current_fov = unreal.PythonBPLib.get_level_viewport_camera_fov()
        try:
            assert 89 < current_fov and current_fov < 93, f"Fov value: {current_fov} != 92 (default value in '/Game/StarterContent/Maps/StarterMap')"
            msg = f"get fov done: {current_fov:.2f}"
        except AssertionError as e:
            succ = False
            msg = str(e)
        self.push_result(succ, msg)



    def record_camera_info(self):

        self.cam_pos, self.cam_rot = unreal.PythonBPLib.get_level_viewport_camera_info()

    def _testcase_camera_info(self):
        succ, msg = True, ""
        self.add_test_log("get_level_viewport_camera_info")
        pos_befor, rot_before = unreal.PythonBPLib.get_level_viewport_camera_info()
        self.add_test_log("set_level_viewport_camera_info")
        unreal.PythonBPLib.set_level_viewport_camera_info(self.cam_pos, self.cam_rot)
        self.add_test_log("viewport_redraw")
        unreal.PythonBPLib.viewport_redraw()
        pos, rot = unreal.PythonBPLib.get_level_viewport_camera_info()

        try:
            assert (pos - self.cam_pos).length() < 1, f"camera pos,  delta: {(pos - self.cam_pos).length()}. {pos} not equal to saved pos: {self.cam_pos} "
            assert rot.is_near_equal(self.cam_rot, error_tolerance=0.1), "camera pos is not equal to save rot"
            msg = f"Camera pos done. delta: {(pos - self.cam_pos).length()} {pos}"
        except AssertionError as e:
            succ = False
            msg = str(e)

        unreal.PythonBPLib.set_level_viewport_camera_info(pos_befor, rot_before)
        self.push_result(succ, msg)

    def _testcase_camera_speed(self):
        succ, msgs = False, []
        try:
            self.add_test_log("get_level_viewport_camera_speed")
            current_speed = unreal.PythonBPLib.get_level_viewport_camera_speed()
            new_speed = current_speed -1 if current_speed > 5 else current_speed + 1
            self.add_test_log("set_level_viewport_camera_speed")
            unreal.PythonBPLib.set_level_viewport_camera_speed(new_speed)
            speed_after = unreal.PythonBPLib.get_level_viewport_camera_speed()
            assert speed_after == new_speed and speed_after != current_speed, f"speed_after: {speed_after} != new_speed: {new_speed} "
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_spawn_camera(self):
        succ, msg = False, ""
        self.add_test_log("spawn_actor_from_class")
        unreal.PythonBPLib.spawn_actor_from_class(unreal.CameraActor
                                                  , unreal.Vector(10, -400, 170)
                                                  , unreal.Rotator(0, 0, 90)
                                                  , select_actors=True)
        try:
            if unreal.PythonBPLib.get_unreal_version()["major"] == 5:
                actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
            else:
                actors = unreal.EditorLevelLibrary.get_selected_level_actors()
            assert len(actors) == 1, f"Selected actor count not match: {len(actors)} vs one camera actor."
            assert actors[0].static_class().get_name() == "CameraActor", "Selected Actor is not CameraActor"
            succ = True
            msg = "Camera Actor Spawned and be selected"
        except AssertionError as e:
            msg = str(e)
        self.push_result(succ, msg)

    def _testcase_pilot_level_actor(self):
        succ, msg = False, ""
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            camera_actors = unreal.PythonBPLib.get_objects_by_class(world, unreal.CameraActor)
            assert len(camera_actors) == 1, "Camera Actor Count != 1"
            camera = camera_actors[0]
            self.add_test_log("pilot_level_actor")
            unreal.PythonBPLib.pilot_level_actor(camera)
            succ = True
        except AssertionError as e:
            msg = str(e)
        self.push_result(succ, msg)

    def _testcase_get_pilot_level_actor(self):
        succ, msg = False, ""
        self.add_test_log("get_pilot_level_actor")
        pilot_actor = unreal.PythonBPLib.get_pilot_level_actor()
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            camera_actors = unreal.PythonBPLib.get_objects_by_class(world, unreal.CameraActor)
            assert pilot_actor == camera_actors[0], f"pilot_actor: {pilot_actor} != {camera_actors[0]}"

            succ = True
        except AssertionError as e:
            msg = str(e)
        self.push_result(succ, msg)

    def _testcase_componnent(self):
        succ, msgs = False, []
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            camera_actors = unreal.PythonBPLib.get_objects_by_class(world, unreal.CameraActor)
            camera = camera_actors[0]
            assert camera, "Camera actor invalid"
            components_in_camera =  camera.get_components_by_class(unreal.ActorComponent)
            scene_comp = camera.get_component_by_class(unreal.SceneComponent)
            assert len(components_in_camera) == 4, "comps in camera actor != 4"
            assert scene_comp, "Can't find scene component in camera actor"
            # select comp
            self.add_test_log("select_component")
            unreal.PythonBPLib.select_component(scene_comp, selected=True, notify=True)
            self.add_test_log("get_selected_components")
            selected = unreal.PythonBPLib.get_selected_components()
            assert selected and len(selected) == 1 and selected[0] == scene_comp, "selected None or not comp"

            msgs.append("Select Component Done.")
            # add comp
            self.add_test_log("add_component")
            unreal.PythonBPLib.add_component(unreal.HierarchicalInstancedStaticMeshComponent, camera, scene_comp)
            comps_after_add = camera.get_components_by_class(unreal.ActorComponent)
            assert len(comps_after_add)== 5, f"Comps count: {len(comps_after_add)} != 5"
            assert camera.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent), "Can't find hism comp in camera"
            msgs.append("Add Component Done.")

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def test_category_viewport(self, id:int):
        self.test_being(id=id)

        level_path = '/Game/StarterContent/Maps/StarterMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)
        self.add_test_log("select_named_actor")
        self.push_call(py_task(unreal.PythonBPLib.select_named_actor, name="Floor_43"), delay_seconds=0.1)
        self.add_test_log("request_viewport_focus_on_selection")
        self.push_call(py_task(unreal.PythonBPLib.request_viewport_focus_on_selection), delay_seconds=0.2)
        self.push_call(py_task(self.record_camera_info), delay_seconds=0.2)

        self.push_call(py_task(unreal.PythonBPLib.select_named_actor, name="Floor_38", clear_selected=False), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.request_viewport_focus_on_selection), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_fov), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_camera_info), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_camera_speed), delay_seconds=0.2)

        # console command

        self.push_call(py_task(unreal.PythonBPLib.execute_console_command, console_command="ShowFlag.MeshEdges 1"), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.execute_console_command, console_command="ShowFlag.MeshEdges 0"), delay_seconds=0.2)

        self.push_call(py_task(self.check_error_in_log), delay_seconds=0.2)


        # view port mode: real_tiem, game_view
        self.push_call(py_task(unreal.PythonBPLib.set_level_viewport_real_time, realtime=False), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.set_level_viewport_real_time, realtime=True), delay_seconds=0.2)
        self.push_call(py_task(self.check_error_in_log), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.set_level_viewport_is_in_game_view, game_view=True), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.set_level_viewport_is_in_game_view, game_view=False), delay_seconds=0.2)
        self.push_call(py_task(self.check_error_in_log), delay_seconds=0.2)

        # spawn camera
        unreal.PythonTestLib.clear_log_buffer()
        self.push_call(py_task(self._testcase_spawn_camera), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_pilot_level_actor), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_get_pilot_level_actor), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.set_level_viewport_locked, locked=True), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.set_level_viewport_locked, locked=False), delay_seconds=0.2)
        self.push_call(py_task(unreal.PythonBPLib.eject_pilot_level_actor), delay_seconds=0.2)
        self.push_call(py_task(self.check_error_in_log), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_componnent), delay_seconds=0.1)

        self.test_finish(id=id)


    def _testcase_properties(self):
        succ, msgs = False, []
        world = unreal.EditorLevelLibrary.get_editor_world()
        actor_id_name = "SkyLight_6"
        actor = unreal.PythonBPLib.find_actor_by_name(actor_id_name, world=world) #
        try:
            assert actor, f"Can't find Actor by name: {actor_id_name}"
            properties = unreal.PythonBPLib.get_all_property_names(unreal.Actor)
            bProperty_name = "bNetTemporary"
            assert bProperty_name in properties, f"Can't find '{bProperty_name}' in unreal.Actor"
            msgs.append("Get Properties Done.")
            # bool
            v = unreal.PythonBPLib.get_bool_property(actor, bProperty_name)
            assert isinstance(v, bool), f"get_bool_property failed. result: {v}"
            msgs.append(f"Get bool property: {bProperty_name} {v}")
            # set
            set_succ = unreal.PythonBPLib.set_bool_property(actor, bProperty_name, False)
            assert set_succ,  f"set_bool_property failed. {bProperty_name}"

            v_afterset = unreal.PythonBPLib.get_bool_property(actor, bProperty_name)
            print(f"{v_afterset} vs {v}")
            assert v_afterset == (not v), f"value after set: {v_afterset} != not value: {v}"


            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_select_assets(self):
        succ, msgs = False, []
        world = unreal.EditorLevelLibrary.get_editor_world()
        actor_label_name = "Chair"
        target_mesh_path = '/Game/StarterContent/Props/SM_Chair'
        self.add_test_log("find_actors_by_label_name")
        mesh_actors = unreal.PythonBPLib.find_actors_by_label_name(actor_label_name, world=world)
        try:
            assert mesh_actors, f"Can't find mesh actor: {actor_label_name}"
            mesh_actor = mesh_actors[0]
            comps = mesh_actor.get_components_by_class(unreal.MeshComponent)
            assert comps and len(comps) == 1, f"mesh component of mesh_actor {len(comps)} != 1"
            mesh = comps[0].get_editor_property("static_mesh")
            assert mesh, f"mesh {actor_label_name}  can't be find"
            mesh_package = mesh.get_outermost()
            assert mesh_package, f"Can't find mesh: {actor_label_name}'s package."
            mesh_asset_path = mesh_package.get_path_name()
            assert mesh_asset_path == target_mesh_path, f"mesh asset path: {mesh_asset_path} != {target_mesh_path}"
            msgs.append(f"Asset path: {mesh_asset_path}")

            # mesh depends on used textures
            self.add_test_log("get_all_deps")
            deps, parent_indexs = unreal.PythonBPLib.get_all_deps(mesh_asset_path, recursive=True)
            assert deps, "deps: None"
            assert_texture_paths = {"/Game/StarterContent/Textures/T_Chair_N", "/Game/StarterContent/Textures/T_Chair_M"}
            assert set(deps) & assert_texture_paths == assert_texture_paths, "Get texture from deps failed."
            msgs.append(f"get_all_deps done.")

            # mesh will be referenced by level
            self.add_test_log("get_all_refs")
            refs, parent_index = unreal.PythonBPLib.get_all_refs(mesh_asset_path, recursive=True)
            assert refs, "refs: None"
            current_level_path = mesh_actor.get_outermost().get_path_name()
            assert current_level_path, "Get level name from mesh failed."
            assert current_level_path in refs, f"Can't find level: {current_level_path} in {assert_texture_paths}'s refs"

            # asset data
            self.add_test_log("get_assets_data_by_package_names")
            asset_datas = unreal.PythonBPLib.get_assets_data_by_package_names([mesh_asset_path, list(assert_texture_paths)[0]])## [a mesh, a texture]
            assert asset_datas and len(asset_datas) == 2, f"get_assets_data_by_package_names failed, len: {len(asset_datas)}"
            texture_asset_data = asset_datas[1]
            asset_folder_path = texture_asset_data.package_path
            assert asset_folder_path and asset_folder_path == "/Game/StarterContent/Textures", f'asset_folder_path == "/Game/StarterContent/Textures"'

            # list_assets_by_class
            self.add_test_log("list_assets_by_class")
            texture_names = unreal.PythonBPLib.list_assets_by_class([asset_folder_path], ['Texture2D'])
            texture_names_in_content = unreal.PythonBPLib.list_assets_by_class(["/Game/"], ['Texture2D'])
            assert len(texture_names) > 80, f"Texture count in folder: {asset_folder_path} <= 80"
            assert len(texture_names) <= len(texture_names_in_content), f"Texture count {len(texture_names)} < {len(texture_names_in_content)}"
            grasstype_names = unreal.PythonBPLib.list_assets_by_class([asset_folder_path], ['LandscapeGrassType'])
            assert len(grasstype_names) == 0, f"Found: {len(grasstype_names)} in folder: {asset_folder_path}"
            msgs.append("list_assets_by_class done.")

            # get_assets_data_by_class, break_soft_object_path
            self.add_test_log("get_assets_data_by_class")
            assets_datas = unreal.PythonBPLib.get_assets_data_by_class([asset_folder_path], ['Texture2D'])
            assert assets_datas, "assets_datas None"
            asset_data = assets_datas[0]
            soft_path = asset_data.to_soft_object_path()
            assert asset_data, "assset_data None"
            self.add_test_log("break_soft_object")
            asset_path_string, sub_path_string = unreal.PythonBPLib.break_soft_object(soft_path)
            assert asset_path_string == asset_data.object_path, f"Get object path from soft_object failed: {asset_data.object_path} vs asset_path_string: {asset_path_string}"
            msgs.append("get_assets_data_by_class/break_soft_object_path done.")

            # get_resource_size
            self.add_test_log("get_resource_size")
            resource_size = unreal.PythonBPLib.get_resource_size(unreal.load_asset(asset_data.object_path), exclusive=False)
            resource_size_exclusive = unreal.PythonBPLib.get_resource_size(unreal.load_asset(asset_data.object_path), exclusive=True)
            assert resource_size and resource_size != resource_size_exclusive, f"get_resource_size, failed: {resource_size} {resource_size_exclusive}"
            msgs.append(f"resource_size done.")

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_asset_exists(self):
        succ, msgs = False, []
        texture_asset_path = "/Game/StarterContent/Textures/T_Shelf_M"
        texture_asset_path_B = "/Game/StarterContent/Textures/T_Spark_Core"
        folders = ["/Game/StarterContent",  "/Game/StarterContent/Props/Materials"]

        project_folder = os.path.abspath(unreal.SystemLibrary.get_project_directory())

        try:
            assert unreal.EditorAssetLibrary.does_asset_exist(texture_asset_path), f"Asset not exist: {texture_asset_path}"
            assert unreal.EditorAssetLibrary.does_asset_exist(texture_asset_path_B), f"Asset not exist: {texture_asset_path_B}"

            for folder in folders:
                if folder.startswith("/Game"):
                    folder = folder.replace("/Game", "/Content")
                folder_path = os.path.join(project_folder, folder[1:] if folder[0] == "/" else folder)
                assert os.path.exists(folder_path), f"Folder path: {folder_path} not exists."
            succ = True
        except AssertionError as e:
            msgs = msgs.append(str(e))

        self.push_result(succ, msgs)

    def check_selected_assets(self, paths):
        succ, msg = False, ""
        try:
            self.add_test_log("get_selected_assets_paths")
            selected = unreal.PythonBPLib.get_selected_assets_paths()
            assert set(paths) & set(selected) == set(paths), f"Selected not equal, {len(paths)} vs {len(selected)}"
            return True
        except AssertionError as e:
            msg = str(e)

        self.push_result(succ, msg)

    def _testcase_create_mat(self, mat_path:str):
        succ, msg = False, ""
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

        try:
            # mat_path.rsplit("/", 1)
            # mat_path = "/Game/_AssetsForTAPythonTestCase/M_CreatedByPython"
            # mat_name, folder = "M_CreatedByPython", "/Game/_AssetsForTAPythonTestCase"
            folder, mat_name = mat_path.rsplit("/", 1)
            math_path = f"{folder}/{mat_name}"
            if unreal.EditorAssetLibrary.does_asset_exist(math_path):
                self.add_test_log("delete_asset")
                unreal.PythonBPLib.delete_asset(math_path, show_confirmation=False)

            my_mat = asset_tools.create_asset(mat_name, folder, unreal.Material, unreal.MaterialFactoryNew())
            unreal.EditorAssetLibrary.save_asset(my_mat.get_path_name())
            math_path = my_mat.get_path_name()
            assert unreal.EditorAssetLibrary.does_asset_exist(math_path), f"Asset not exist: {math_path}"

            succ = True
        except AssertionError as e:
            msg = str(e)
        self.push_result(succ, msg)

    def _testcase_sync_asset(self, asset_path):
        succ, msgs = False, []
        try:
            assert unreal.EditorAssetLibrary.does_asset_exist(asset_path), f"Asset not exist: {asset_path}"
            asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
            assert asset_data, "assert_data: None"
            self.add_test_log("sync_to_assets")
            unreal.PythonBPLib.sync_to_assets([asset_data], allow_locked_browsers=True, focus_content_browser=True)
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_set_folder_color(self, folder_path):
        succ, msg = False, ""
        try:
            self.add_test_log("set_folder_color")
            unreal.PythonBPLib.set_folder_color(folder_path, unreal.LinearColor.GREEN)
            succ = True
        except AssertionError as e:
            msg = str(e)
        self.push_result(succ, msg)

    def _testcase_set_folder_in_content_browser(self, folders:[str]):
        succ, msg = False, ""
        try:
            assert isinstance(folders, list), "param folder need a string list"
            self.add_test_log("set_selected_folder")
            unreal.PythonBPLib.set_selected_folder(folders)
            self.add_test_log("get_selected_folder")
            current_selectd = unreal.PythonBPLib.get_selected_folder()
            assert folders == current_selectd, f"set_folder_in_content_browser  not equal"
            succ = True
        except AssertionError as e:
            msg = str(e)
        self.push_result(succ, msg)

    def _testcase_assets_editor(self, bOpen):
        succ, msg = False, ""
        texture_asset_path = "/Game/StarterContent/Textures/T_Shelf_M"
        mat_asset_path = "/Game/_AssetsForTAPythonTestCase/M_CreatedByPython"
        assets = [unreal.load_asset(p) for p in [texture_asset_path, mat_asset_path]]
        try:
            if bOpen:
                unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets(assets)
            else:
                self.add_test_log("close_editor_for_assets")
                unreal.PythonBPLib.close_editor_for_assets(assets)
            succ = True
        except AssertionError as e:
            msg = str(e)

        self.push_result(succ, msg)

    def _testcase_bp_hierarchy(self):
        succ, msgs = False, []
        try:
            bp_c_path = '/Game/_AssetsForTAPythonTestCase/BP/BP_C'
            bp_c = unreal.load_asset(bp_c_path)
            assert bp_c, "bp_c asset not exists."

            self.add_test_log("spawn_actor_from_object")
            bp_c_instance = unreal.PythonBPLib.spawn_actor_from_object(bp_c, unreal.Vector.ZERO, select_actors=True)
            if unreal.PythonBPLib.get_unreal_version()["major"] == 5:
                actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
            else:
                actors = unreal.EditorLevelLibrary.get_selected_level_actors()

            assert len(actors) == 1, f"selected_actor != 0, actor: {len(actors)}"
            bp_actor = actors[0]
            assert bp_actor.get_actor_label() == bp_c_path.rsplit('/', 1)[-1], f"bp_actor label name {bp_actor.get_actor_label()} != { bp_c_path.rsplit('/', 1)[-1]}"

            assert bp_actor == bp_c_instance, " bp_actor != bp_c_instance"
            self.add_test_log("get_bp_class_hierarchy_package")
            hierarchy_packages = unreal.PythonBPLib.get_bp_class_hierarchy_package(bp_actor.get_class())
            assert len(hierarchy_packages) == 3, f"hierarchy_packages len: {len(hierarchy_packages)} != 3, "
            for i, (package, target_name) in enumerate(zip(hierarchy_packages, ["/BP/BP_C", "/BP/BP_B", "/BP/BP_A"])):
                assert package.get_name().endswith(target_name), f"index {i} package: {package.get_name()} != {target_name}"
                msgs.append(f"BP Hierarchy {i}: {package}")

            # apply
            custom_value_in_c = bp_c_instance.get_editor_property("CustomValueInC")
            new_value_for_c = unreal.Vector.ONE if custom_value_in_c.is_nearly_zero() else unreal.Vector.ZERO
            # bp_c_instance.set_editor_property("CustomValueInC", new_value_for_c)  <- error
            unreal.PythonBPLib.set_vector_property(bp_c_instance, "CustomValueInC", new_value_for_c)
            self.add_test_log("apply_instance_changes_to_blueprint")
            unreal.PythonBPLib.apply_instance_changes_to_blueprint(bp_c_instance)

            # bp_c = unreal.load_asset(bp_c_path)
            self.add_test_log("spawn_actor_from_object")
            bp_c_instance_after = unreal.PythonBPLib.spawn_actor_from_object(bp_c, unreal.Vector.ZERO, select_actors=True)

            assert bp_c_instance_after.get_editor_property("CustomValueInC").is_near_equal(new_value_for_c)\
                , f'CustomValueInC from new bp_c: {bp_c_instance_after.get_editor_property("CustomValueInC")} != {new_value_for_c}'

            msgs.append("apply_instance_changes_to_blueprint ok")
            # diff assets
            bp_b_path = '/Game/_AssetsForTAPythonTestCase/BP/BP_B'
            bp_b = unreal.load_asset(bp_b_path)
            self.add_test_log("diff_assets")
            unreal.PythonBPLib.diff_assets(bp_b, bp_c)

            msgs.append("diff_assets ok")
            self.add_test_log("get_blueprint_generated_class")
            assert bp_b.generated_class() == unreal.PythonBPLib.get_blueprint_generated_class(bp_b), "get_blueprint_generated_class assert failed."

            return True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_close_bp_diff_window(self):
        bp_b = unreal.load_asset('/Game/_AssetsForTAPythonTestCase/BP/BP_B')
        bp_c = unreal.load_asset('/Game/_AssetsForTAPythonTestCase/BP/BP_C')

        self.add_test_log("close_editor_for_assets")
        unreal.PythonBPLib.close_editor_for_assets([bp_b, bp_c])

    def _testcase_function_and_property(self):
        succ, msgs = False, []
        try:
            bp_path = '/Game/_AssetsForTAPythonTestCase/BP/BP_C'
            test_bp = unreal.load_asset(bp_path)
            assert test_bp, "test_bp assert None"

            bp_actor = unreal.PythonBPLib.spawn_actor_from_object(test_bp, unreal.Vector.BACKWARD * 100)
            assert bp_actor, "bp_actor None"
            # 1. call function
            self.add_test_log("call_function")
            unreal.PythonBPLib.call_function(bp_actor, "TestFunction 10.14")
            # 2. object flags
            self.add_test_log("get_object_flags")
            flag_values = unreal.PythonBPLib.get_object_flags(bp_actor)
            assert flag_values == 8, "flag_values != 8, RF_Transactional =0x00000008"  # more info: Utilities.Utils.py
            # 3. string
            self.add_test_log("get_string_property")
            str_before = unreal.PythonBPLib.get_string_property(bp_actor, "AStringValue")
            self.add_test_log("set_string_property")
            unreal.PythonBPLib.set_string_property(bp_actor, "AStringValue", "SomeValueFromPython")
            str_After = unreal.PythonBPLib.get_string_property(bp_actor, "AStringValue")
            assert str_before == "", f"str_before: {str_before} != '' "
            assert str_After == "SomeValueFromPython", f"str_After: {str_After} != 'SomeValueFromPython' "

            # 4. bool
            self.add_test_log("get_bool_property")
            bool_before = unreal.PythonBPLib.get_bool_property(bp_actor, "ABoolValue")
            self.add_test_log("set_bool_property")
            unreal.PythonBPLib.set_bool_property(bp_actor, "ABoolValue", True)
            bool_after = unreal.PythonBPLib.get_bool_property(bp_actor, "ABoolValue")
            assert not bool_before, f"bool_before: {bool_before} != False "
            assert bool_after, f"bool_After: {bool_after} != True "

            # 5. int
            self.add_test_log("get_int_property")
            int_before = unreal.PythonBPLib.get_int_property(bp_actor, "AIntValue")
            self.add_test_log("set_int_property")
            unreal.PythonBPLib.set_int_property(bp_actor, "AIntValue", 45678)
            int_after = unreal.PythonBPLib.get_bool_property(bp_actor, "AIntValue")
            assert not int_before, f"int_before: {int_before} != 0 "
            assert int_after, f"int_after: {int_before} != 45678"

            # 6. float
            self.add_test_log("get_float_property")
            float_before = unreal.PythonBPLib.get_float_property(bp_actor, "AFloatValue")
            self.add_test_log("set_float_property")
            unreal.PythonBPLib.set_float_property(bp_actor, "AFloatValue", 123.45)
            float_after = unreal.PythonBPLib.get_float_property(bp_actor, "AFloatValue")
            assert not float_before, f"float_before: {float_before} != 0 "
            assert abs(float_after - 123.45) < 0.00001, f"float_After: {float_after} != 123.45 "

            # 7. vector
            self.add_test_log("get_vector_property")
            vector_before = unreal.PythonBPLib.get_vector_property(bp_actor, "AVectorValue")
            self.add_test_log("set_vector_property")
            unreal.PythonBPLib.set_vector_property(bp_actor, "AVectorValue", unreal.Vector.ONE)
            vector_after = unreal.PythonBPLib.get_vector_property(bp_actor, "AVectorValue")
            assert unreal.Vector.is_nearly_zero(vector_before), f"vector_before: {vector_before} != vector.zero"
            assert unreal.Vector.is_near_equal(vector_after, unreal.Vector.ONE), f"float_After: {vector_after} != vector.one"

            # 8. object
            mesh = unreal.load_asset('/Game/StarterContent/Props/SM_Lamp_Ceiling')
            assert mesh, f"mesh: SM_Lamp_Ceiling None"
            self.add_test_log("get_object_property")
            object_before = unreal.PythonBPLib.get_object_property(bp_actor, "AMeshValue")
            self.add_test_log("set_object_property")
            unreal.PythonBPLib.set_object_property(bp_actor, "AMeshValue", mesh)
            object_after = unreal.PythonBPLib.get_object_property(bp_actor, "AMeshValue")
            assert None == object_before, f"object_before: {object_after} != None"
            assert object_after == mesh, f"object_after: {object_after} != loaded mesh "
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_save_thumbnail(self):
        succ, msgs = False, []
        try:
            asset_path = '/Game/StarterContent/Props/SM_Chair.SM_Chair'
            asset_name = os.path.basename(asset_path.split(".")[0])
            export_path = os.path.join(unreal.SystemLibrary.get_project_directory(), r"Saved/Screenshots/4TestCase_{}.png".format(asset_name))
            if os.path.exists(export_path):
                os.remove(export_path)

            self.add_test_log("save_thumbnail")
            unreal.PythonBPLib.save_thumbnail(asset_path, output_path=export_path)

            assert os.path.exists(export_path), f"Export thumbnail not exists: {export_path}"

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_export_map(self):
        succ, msgs = False, []
        try:
            export_path = os.path.join(unreal.SystemLibrary.get_project_directory(),r"Saved/Export/4TestCase.obj")
            if os.path.exists(export_path):
                os.remove(export_path)

            self.add_test_log("find_actors_by_label_name")
            actors = unreal.PythonBPLib.find_actors_by_label_name("Chair", world=unreal.EditorLevelLibrary.get_editor_world())
            assert actors and len(actors) > 0, f"Find actor: Chair failed. actors None"

            self.add_test_log("export_map")
            unreal.PythonBPLib.export_map(actors[0], export_path, export_selected_actors_only=True)
            assert os.path.exists(export_path), f"Export map failed: {export_path}"
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)


    def test_category_assets(self, id:int):
        self.test_being(id=id)
        self.push_call(py_task(self.check_error_in_log), delay_seconds=0.2)

        level_path = '/Game/StarterContent/Maps/StarterMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_select_assets), delay_seconds=0.1)
        # self.push_call(py_task(self._testcase_content_browser), delay_seconds=0.3)

        texture_asset_path = "/Game/StarterContent/Textures/T_Shelf_M"
        texture_asset_path_B = "/Game/StarterContent/Textures/T_Spark_Core"

        self.push_call(py_task(self._testcase_asset_exists), delay_seconds=0.1)

        self.add_test_log("set_selected_assets_by_paths")
        self.push_call(py_task(unreal.PythonBPLib.set_selected_assets_by_paths, paths=[texture_asset_path]), delay_seconds=0.1)
        self.push_call(py_task(self.check_selected_assets, paths=[texture_asset_path]), delay_seconds=0.5)

        self.push_call(py_task(unreal.PythonBPLib.set_selected_assets_by_paths, paths=[texture_asset_path, texture_asset_path_B]), delay_seconds=0.1)
        self.push_call(py_task(self.check_selected_assets, paths=[texture_asset_path, texture_asset_path_B]), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_create_mat, mat_path="/Game/_AssetsForTAPythonTestCase/M_CreatedByPython"), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_sync_asset, asset_path="/Game/_AssetsForTAPythonTestCase/M_CreatedByPython"), delay_seconds=0.3)

        # folder color
        self.push_call(py_task(self._testcase_set_folder_color, folder_path="/Game/_AssetsForTAPythonTestCase"), delay_seconds=0.2)
        self.add_test_log("clear_folder_color")
        self.push_call(py_task(unreal.PythonBPLib.clear_folder_color, folder_path="/Game/_AssetsForTAPythonTestCase"), delay_seconds=0.2)        # self.push_call(py_task(self._testcase_select_assets), delay_seconds=0.1)
        # self.push_call(py_task(self._testcase_content_browser), delay_seconds=0.3)

        texture_asset_path = "/Game/StarterContent/Textures/T_Shelf_M"
        texture_asset_path_B = "/Game/StarterContent/Textures/T_Spark_Core"

        self.push_call(py_task(self._testcase_asset_exists), delay_seconds=0.1)

        self.push_call(py_task(unreal.PythonBPLib.set_selected_assets_by_paths, paths=[texture_asset_path]), delay_seconds=0.1)
        self.push_call(py_task(self.check_selected_assets, paths=[texture_asset_path]), delay_seconds=0.5)

        self.push_call(py_task(unreal.PythonBPLib.set_selected_assets_by_paths, paths=[texture_asset_path, texture_asset_path_B]), delay_seconds=0.1)
        self.push_call(py_task(self.check_selected_assets, paths=[texture_asset_path, texture_asset_path_B]), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_create_mat, mat_path="/Game/_AssetsForTAPythonTestCase/M_CreatedByPython"), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_sync_asset, asset_path="/Game/_AssetsForTAPythonTestCase/M_CreatedByPython"), delay_seconds=0.3)


        self.push_call(py_task(self._testcase_set_folder_in_content_browser, folders=["/Game/StarterContent/HDRI"]), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_set_folder_in_content_browser, folders=["/Engine/Animation"
                                , "/Engine/ArtTools", "/Engine/Automation"]), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_set_folder_in_content_browser, folders=["/Game/StarterContent/HDRI"]),delay_seconds=0.2)

        # asset editor
        self.push_call(py_task(self._testcase_assets_editor, bOpen=True), delay_seconds=0.5)
        self.push_call(py_task(self._testcase_assets_editor, bOpen=False), delay_seconds=1)

        self.push_call(py_task(self.check_error_in_log), delay_seconds=0.2)

        self.push_call(py_task(self._testcase_bp_hierarchy), delay_seconds=0.2)
        self.push_call(py_task(self._testcase_close_bp_diff_window), delay_seconds=0.5)

        self.push_call(py_task(self._testcase_function_and_property), delay_seconds=0.1)

        self.push_call(py_task(self.check_error_in_log), delay_seconds=0.2)

        self.push_call(py_task(self._testcase_save_thumbnail), delay_seconds=0.1)

        level_path = '/Game/StarterContent/Maps/StarterMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_export_map), delay_seconds=0.5)

        self.test_finish(id=id)


    def _testcase_multi_line_trace(self):
        succ, msgs = False, []
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            start_locs = [unreal.Vector(x * 100, 0, 10_00) for x in range(15)]
            end_locs = [unreal.Vector(x * 100, 0, -10_00) for x in range(15)]

            profile_name = "BlockAll"
            draw_debug_type = unreal.DrawDebugTrace.FOR_DURATION
            draw_time = 3
            bHit, hitLocs = unreal.PythonBPLib.multi_line_trace_at_once_by_profile(world, start_locs, end_locs, profile_name, draw_debug_type, draw_time)
            msgs.append(f"multi_line_trace_at_once_by_profile hit: {bHit}")
            succ = True

        except AssertionError as e:
            msgs.append(str(e))
        self.push_result(succ, msgs)

    def _testcase_sample_height(self):
        succ, msgs = False, []
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            center = unreal.Vector(0, 0, 0)
            width = 50_00
            height = 50_00
            grid_size = 100
            trace_depth = 10_00
            profile_name = "BlockAll"
            draw_debug_type = unreal.DrawDebugTrace.FOR_DURATION
            draw_time = 3
            default_height = 0
            x_count, y_count, hit_locs = unreal.PythonBPLib.sample_heights(world, center, width, height, grid_size, trace_depth, profile_name,
                                              draw_debug_type, draw_time, default_height)

            msgs.append(f"Sampler x_count: {x_count}, y_count: {y_count}, hit_locs = {len(hit_locs)}")
            unreal.PythonBPLib.viewport_redraw()

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_gc(self):
        succ, msgs = False, []
        try:
            for i in range(10000):
                o = unreal.Actor()
            unreal.PythonBPLib.gc(0)
            succ = True
        except AssertionError as e:
            msgs.append(str(e))
        self.push_result(succ, msgs)

    def _testcase_redirectors(self):
        succ, msgs = False, []
        try:
            unreal.PythonBPLib.get_redirectors_destination_object()
            pass
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_clearup_material(self):
        succ, msgs = False, []
        try:
        # 0: delete model that used the material
            world = unreal.EditorLevelLibrary.get_editor_world()
            assert world.get_name() == "NewMap", "Need load Level: NewMap"

            chair_asset = unreal.load_asset('/Game/StarterContent/Props/SM_Chair')
            mesh_actors = unreal.PythonBPLib.get_objects_by_class(world, unreal.StaticMeshActor)
            if mesh_actors:
                for actor in mesh_actors:
                    if actor.static_mesh_component.static_mesh == chair_asset:
                        actor.destroy_actor()
        # 1: save and open another level
            unreal.EditorLevelLibrary.save_current_level()
            unreal.EditorLevelLibrary.load_level('/Game/StarterContent/Maps/StarterMap')

        # 2: fixup redirector, delete material assets
            mat_path = "/Game/_AssetsForTAPythonTestCase/Materials/M_Ori"
            new_mat_path = "/Game/_AssetsForTAPythonTestCase/Materials/NewPath/M_Ori"
            for path in [mat_path, new_mat_path]:
                if unreal.EditorAssetLibrary.does_asset_exist(path):
                    asset = unreal.load_asset(path)
                    if isinstance(asset, unreal.ObjectRedirector):
                        self.add_test_log("fix_up_redirectors")
                        unreal.PythonBPLib.fix_up_redirectors([path])
                    else:
                        asset = None
                        self.add_test_log("delete_asset")
                        unreal.PythonBPLib.delete_asset(path, show_confirmation=False)
            succ = True
            msgs.append("ori material deleted")
        except AssertionError as e:
            msgs.append(str(e))
        self.push_result(succ, msgs)


    def _testcase_create_mat_redirector(self):
        # 0: create material
        succ, msgs = False, []
        try:
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

            mat_path = "/Game/_AssetsForTAPythonTestCase/Materials/M_Ori"
            folder, mat_name = mat_path.rsplit("/", 1)

            if unreal.EditorAssetLibrary.does_asset_exist(mat_path):
                unreal.PythonBPLib.delete_asset(mat_path, show_confirmation=False)

            my_mat = asset_tools.create_asset(mat_name, folder, unreal.Material, unreal.MaterialFactoryNew())
            unreal.EditorAssetLibrary.save_asset(my_mat.get_path_name())

            assert unreal.EditorAssetLibrary.does_asset_exist(mat_path), f"Asset not exist: {mat_path}"
            # 1:
            # create mesh actor for material
            chair_asset = unreal.load_asset('/Game/StarterContent/Props/SM_Chair')
            chair_actor = unreal.PythonBPLib.spawn_actor_from_object(chair_asset, unreal.Vector.ZERO, select_actors=True)
            mat_name, folder = "M_Ori", "/Game/_AssetsForTAPythonTestCase/Materials"

            if unreal.EditorAssetLibrary.does_asset_exist(mat_path):
                mat = unreal.load_asset(mat_path)
            else:
                mat = asset_tools.create_asset(mat_name, folder, unreal.Material, unreal.MaterialFactoryNew())
                unreal.EditorAssetLibrary.save_asset(mat.get_path_name())

            chair_actor.static_mesh_component.set_material(0, mat)

            assert unreal.EditorAssetLibrary.does_asset_exist(mat_path), f"Asset not exist: {mat_path}"
            unreal.EditorLevelLibrary.save_current_level()

            # 2: save and open another level
            unreal.EditorLevelLibrary.load_level('/Game/StarterContent/Maps/StarterMap')
            # 3:
            new_mat_path = "/Game/_AssetsForTAPythonTestCase/Materials/NewPath/M_Ori"
            unreal.EditorAssetLibrary.rename_asset(mat_path, new_mat_path)

            assert unreal.EditorAssetLibrary.does_asset_exist(new_mat_path), "Moved material not exists."

            # 4: assert
            redirector_path = mat_path
            dest_path = unreal.load_asset(redirector_path).get_outermost().get_path_name()
            assert dest_path != mat_path and dest_path == new_mat_path, f"destination path: {dest_path} not equal to the new path {mat_path}"
            self.add_test_log("gc")
            unreal.PythonBPLib.gc(0)

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_fixup_redirector(self):
        succ, msgs = True, []
        try:
            self.add_test_log("fix_up_redirectors_in_folder")
            unreal.PythonBPLib.fix_up_redirectors_in_folder(["/Game/_AssetsForTAPythonTestCase/Materials"])
            mat_path = "/Game/_AssetsForTAPythonTestCase/Materials/M_Ori"
            assert False == unreal.EditorAssetLibrary.does_asset_exist(mat_path), "redirector still exists."
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def test_category_redirector(self, id):
        self.test_being(id=id)
        level_path = '/Game/_AssetsForTAPythonTestCase/Maps/NewMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_clearup_material), delay_seconds=0.1)

        level_path = '/Game/_AssetsForTAPythonTestCase/Maps/NewMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_create_mat_redirector), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_fixup_redirector), delay_seconds=0.5)

        self.test_finish(id)


    def _delete_assets(self, asset_paths : List[str]):
        for path in asset_paths:
            if unreal.EditorAssetLibrary.does_asset_exist(path):
                unreal.PythonBPLib.delete_asset(path, show_confirmation=False)
                print(f"== Delete: {path}")

    def _testcase_user_defined_enum(self):
        succ, msgs = False, []
        try:
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            # 1 create a enum
            enum_name = "IAmAEnum"
            enum_path = f"{self.temp_assets_folder}/{enum_name}"
            # assert False == unreal.EditorAssetLibrary.does_asset_exist(enum_path), f"enum has already exists: {enum_path}"
            created_enum = asset_tools.create_asset(enum_name, self.temp_assets_folder, unreal.UserDefinedEnum, unreal.EnumFactory())
            assert created_enum, "created_enum_failed"
            msgs.append("Enum created.")
            self.add_test_log("set_selected_assets_by_paths")
            unreal.PythonBPLib.set_selected_assets_by_paths([enum_path])
            # unreal.EditorAssetLibrary.save_asset(created_enum.get_path_name())

            # 2 Set items
            assert created_enum, "created_enum None"
            items = ["A", "BB", "CCC", "DDDD", "EEEEE"]
            self.add_test_log("set_enum_items")
            unreal.PythonEnumLib.set_enum_items(created_enum, items)
            msgs.append(f"Enum items set.")

            # 3 move item
            self.add_test_log("move_enum_item")
            unreal.PythonEnumLib.move_enum_item(created_enum, 1, 3)
            msgs.append(f"Enum item moved.")

            # 4 bigflags
            self.add_test_log("is_bitflags_type")
            bBitFlats = unreal.PythonEnumLib.is_bitflags_type(created_enum)
            assert bBitFlats == False, f"created_enum bitflags assert failed,  current: {bBitFlats}"

            self.add_test_log("set_bitflags_typ")
            unreal.PythonEnumLib.set_bitflags_type(created_enum, True)
            assert bBitFlats == False, f"created_enum bitflags assert failed, after set,  current: {bBitFlats}"
            msgs.append(f"Enum bitflags set.")
            # 5
            self.add_test_log("set_display_name")
            self.add_test_log("set_description_by_index")
            for i in range(len(items)):
                unreal.PythonEnumLib.set_display_name(created_enum, i, "iAmItem_{}".format(i))
                unreal.PythonEnumLib.set_description_by_index(created_enum, i, f"item description {i}")

            created_enum.set_editor_property("enum_description", "Enum Description")
            msgs.append(f"Enum names set.")

            # 6 check
            moved_order = [i for i in range(5)]
            temp = moved_order.pop(1)
            moved_order.insert(3, temp)

            for i in range(unreal.PythonEnumLib.get_enum_len(created_enum)):
                if i == 0:
                    self.add_test_log("get_name_by_index")
                name = unreal.PythonEnumLib.get_name_by_index(created_enum, i)

                if i == 0:
                    self.add_test_log("get_display_name_by_index")
                display_name = unreal.PythonEnumLib.get_display_name_by_index(created_enum, i)

                if i == 0:
                    self.add_test_log("get_description_by_index")
                description = unreal.PythonEnumLib.get_description_by_index(created_enum, i)
                print("\t{}: {}: {}, desc: ".format(i, unreal.PythonEnumLib.get_name_by_index(created_enum, i)
                                                    , unreal.PythonEnumLib.get_display_name_by_index(created_enum, i)
                                                    , unreal.PythonEnumLib.get_description_by_index(created_enum, i)
                                                    ))
                assert name == f"IAmAEnum::NewEnumerator{moved_order[i]}", f"name assert fail: {name} vs IAmAEnum::NewEnumerator{moved_order[i]}"
                assert display_name == f"iAmItem_{i}", f"display_name assert fail: {display_name}"
                assert description == f"item description {i}", f"description assert fail: {description}"

            bFound = False
            self.add_test_log("get_display_name_map")
            for name, display_name in unreal.PythonEnumLib.get_display_name_map(created_enum).items():
                if name == "NewEnumerator1":
                    assert display_name == "iAmItem_3", f"assert display name failed: '{display_name}' vs 'iAmItem_3'"
                    bFound = True
                    break
            assert bFound, "Assert 'NewEnumerator1' in created enum failed."

            self.add_test_log("get_cpp_form")
            cpp_form = unreal.PythonEnumLib.get_cpp_form(created_enum)
            assert cpp_form == 1, "cpp_form != 1"
            cpp_dict = {0: "Regular", 1: "Namespaced", 2: "EnumClass"}
            msgs.append(f"Enum cpp form: {cpp_dict[cpp_form]}")
            unreal.EditorAssetLibrary.save_asset(created_enum.get_path_name())
            created_enum = None

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_user_defined_struct(self):
        succ, msgs = False, []
        try:
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            # 1 create a struct
            struct_name = "IAmAStruct"
            struct_path = f"{self.temp_assets_folder}/{struct_name}"
            msgs.append(f"struct_path: {struct_path}")
            created_struct = asset_tools.create_asset(struct_name, self.temp_assets_folder, unreal.UserDefinedStruct, unreal.StructureFactory())
            assert created_struct, "created_struct_failed"
            msgs.append("Struct created.")
            # 2 add items
            self.add_test_log("add_variable")
            unreal.PythonStructLib.add_variable(created_struct, category="real", sub_category="double",
                                                sub_category_object=None, container_type_value=1, # array
                                                is_reference=False, friendly_name="my_float_vars")
            unreal.PythonStructLib.add_variable(created_struct, "bool", "", None, 0, False, friendly_name="my_bool_var")
            unreal.PythonStructLib.add_variable(created_struct, "struct", "", unreal.Transform.static_struct(), 0, False, "my_transform_var")
            unreal.PythonStructLib.add_variable(created_struct, "object", "", unreal.StaticMesh.static_class(), 0, False, "my_mesh_var")
            unreal.PythonStructLib.add_variable(created_struct, "object", "", unreal.StaticMesh.static_class(), 0, False, "another_mesh_var")
            self.add_test_log("add_directory_variable")
            unreal.PythonStructLib.add_directory_variable(created_struct, category="name", sub_category="", sub_category_object=None
                                                          , terminal_category="object", terminal_sub_category="",
                                                          terminal_sub_category_object=unreal.StaticMesh.static_class()
                                                          , is_reference=False, friendly_name="name_to_mesh_dict")

            # 3.remove the default bool variable, and save the struct
            self.add_test_log("remove_variable_by_name")
            unreal.PythonStructLib.remove_variable_by_name(created_struct, unreal.PythonStructLib.get_variable_names(created_struct)[0])
            msgs.append("Remove default bool var.")

            # 4. log_var_desc
            self.add_test_log("clear_log_buffer")
            unreal.PythonTestLib.clear_log_buffer()
            self.add_test_log("log_var_desc")
            unreal.PythonStructLib.log_var_desc(created_struct)
            self.add_test_log("get_logs")
            logs = unreal.PythonTestLib.get_logs(-1, category_regex="PythonTA")
            assert logs, "Logs None"
            assert "Var 0: my_float_vars" in logs[0], "Can't find: Var 0: my_float_vars"

            print("-" * 80)
            # 5
            unreal.PythonTestLib.clear_log_buffer()
            self.add_test_log("log_var_desc_by_friendly_name")
            unreal.PythonStructLib.log_var_desc_by_friendly_name(created_struct, "my_transform_var")
            logs = unreal.PythonTestLib.get_logs(-1, category_regex="PythonTA")
            assert logs, "logs None"

            self.add_test_log("get_variable_description")
            description = unreal.PythonStructLib.get_variable_description(created_struct, "my_transform_var")
            assert description, "description None"
            assert "FriendlyName" in description, "FriendlyName not in get_variable_description()"
            assert description["FriendlyName"] == "my_transform_var", "Friendly Name != my_transform_var"
            msgs.append("Get var desc.")
            # 6
            self.add_test_log("get_guid_from_friendly_name")
            guid = unreal.PythonStructLib.get_guid_from_friendly_name(created_struct, "my_transform_var")
            assert description["VarGuid"] == guid.to_string(), f"VarGuid in description: {description['VarGuid']} != {str(guid)}"
            msgs.append("get_guid_from_friendly_name.")

            #7
            self.add_test_log("is_unique_friendly_name")
            assert False == unreal.PythonStructLib.is_unique_friendly_name(created_struct, "my_transform_var"), "my_transform_var not unique friendly name"
            assert unreal.PythonStructLib.is_unique_friendly_name(created_struct, "my_dict_var"), "my_transform_var is not unique friendly name"
            # 8 default value of var
            transform_guid = unreal.PythonStructLib.get_guid_from_friendly_name(created_struct, "my_transform_var")
            self.add_test_log("get_variable_default_value 1")
            defualt_value = unreal.PythonStructLib.get_variable_default_value(created_struct, transform_guid)
            assert defualt_value == '0.000000,0.000000,0.000000|0.000000,0.000000,-0.000000|1.000000,1.000000,1.000000', f"default_value: {defualt_value} assert failed"
            self.add_test_log("change_variable_default_value")
            unreal.PythonStructLib.change_variable_default_value(created_struct, transform_guid
                                                            , "0, 1, 2|20, 30, 10|1, 2, 3")
            self.add_test_log("get_variable_default_value 2")
            new_defualt_value = unreal.PythonStructLib.get_variable_default_value(created_struct, transform_guid)
            assert new_defualt_value == '0.000000,1.000000,2.000000|20.000000,30.000000,10.000000|1.000000,2.000000,3.000000' or new_defualt_value == "0, 1, 2|20, 30, 10|1, 2, 3"\
                    , f"new_defualt_value assert failed: {new_defualt_value} len:{len(new_defualt_value)}"

            msgs.append("log var. ")

            # 9. names
            self.add_test_log("get_friendly_names")
            friend_names = unreal.PythonStructLib.get_friendly_names(created_struct)
            self.add_test_log("get_variable_names")
            var_names = unreal.PythonStructLib.get_variable_names(created_struct)
            assert len(friend_names) == len(var_names), f"len(friend_names): {len(friend_names)} != len(var_names): {len(var_names)}"

            assert "another_mesh_var" in friend_names, "another_mesh_var not in friend names"

            # 10. remove
            need_remove_var_name = None
            for name in unreal.PythonStructLib.get_variable_names(created_struct):
                if str(name).startswith("another_mesh_var"):
                    need_remove_var_name = name
            assert need_remove_var_name, "Can't find another mesh var"
            self.add_test_log("remove_variable_by_name")
            unreal.PythonStructLib.remove_variable_by_name(created_struct, need_remove_var_name)
            assert "another_mesh_var" not in unreal.PythonStructLib.get_friendly_names(created_struct), "Still 'another_mesh_var' var in struct"
            msgs.append("remove var.")

            for i, name in enumerate(unreal.PythonStructLib.get_friendly_names(created_struct)):
                if i == 0:
                    self.add_test_log("get_guid_from_property_name")
                guid = unreal.PythonStructLib.get_guid_from_property_name(name)
                if i == 0:
                    self.add_test_log("rename_variable")
                unreal.PythonStructLib.rename_variable(created_struct, guid, f"renamed_{name}")

            unreal.EditorAssetLibrary.save_asset(struct_path)

            succ = True
        except Exception as e:
            msgs.append(str(e))
        self.push_result(succ, msgs)

    def _testcase_user_datatable(self):
        # need struct
        succ, msgs = False, []
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        try:
            # 1. create
            datatable_name = "IAmADataTable"
            datatable_path = f"{self.temp_assets_folder}/{datatable_name}"
            struct_name = "IAmAStruct"
            struct_path = f"{self.temp_assets_folder}/{struct_name}"

            factory = unreal.DataTableFactory()
            factory.struct = unreal.load_asset(struct_path)

            created_datatable = asset_tools.create_asset(datatable_name, self.temp_assets_folder, unreal.DataTable, factory)

            assert created_datatable, "created_datatable_failed"
            msgs.append("datatable created.")
            # 2. add row
            for i in range(3):
                if i == 0:
                    self.add_test_log("add_row")
                unreal.PythonDataTableLib.add_row(created_datatable, f"MyRow_{i}")

            self.add_test_log("get_row_names")
            row_names = unreal.PythonDataTableLib.get_row_names(created_datatable)
            assert len(row_names) == 3, f"len(row_names): {len(row_names)} != 3"
            for i in range(3):
                if i == 0:
                    self.add_test_log("get_row_name")
                _row_name = unreal.PythonDataTableLib.get_row_name(created_datatable, i)
                assert _row_name == row_names[i], f"get_row_name: {_row_name} != get_row_names[i]: {row_names[i]}"

            # 3. move row
            # 0, 1, 2
            self.add_test_log("move_row")
            unreal.PythonDataTableLib.move_row(created_datatable, "MyRow_0", up=False, num_rows_to_move_by=2)
            self.add_test_log("get_row_names")
            assert unreal.PythonDataTableLib.get_row_names(created_datatable) == ["MyRow_1", "MyRow_2", "MyRow_0"], "Row not match after move row0 down 2"
            unreal.PythonDataTableLib.move_row(created_datatable, "MyRow_2", up=False, num_rows_to_move_by=1)
            assert unreal.PythonDataTableLib.get_row_names(created_datatable) == ["MyRow_1", "MyRow_0", "MyRow_2"], "Row not match after move row2 down 1"
            unreal.PythonDataTableLib.move_row(created_datatable, "MyRow_0", up=True, num_rows_to_move_by=1), "Row not match after move row0 up 1"
            # back to 0, 1, 2

            msgs.append("Add row.")
            # 4. remove row
            self.add_test_log("remove_row")
            unreal.PythonDataTableLib.remove_row(created_datatable, "MyRow_1")
            row_names = unreal.PythonDataTableLib.get_row_names(created_datatable)
            assert row_names == ["MyRow_0", "MyRow_2"], "row name assert failed: {}".format(" ,".join(row_names))
            msgs.append("Remove row.")

            # 5. rename
            self.add_test_log("rename_row")
            unreal.PythonDataTableLib.rename_row(created_datatable,  "MyRow_2",  "MyRow_1")
            row_names = unreal.PythonDataTableLib.get_row_names(created_datatable)
            assert row_names == ["MyRow_0", "MyRow_1"], "row name assert failed: {}".format(" ,".join(row_names))
            msgs.append("Rename row.")

            # 6. struct
            self.add_test_log("get_data_table_struct_path")
            struct_path_from_datatable = unreal.PythonDataTableLib.get_data_table_struct_path(created_datatable)
            self.add_test_log("get_data_table_struct")
            struct_from_datatable = unreal.PythonDataTableLib.get_data_table_struct(created_datatable)
            assert struct_path_from_datatable == struct_path, f"struct_path_from_datatable: {struct_path_from_datatable} != struct_path: {struct_path} "
            assert struct_from_datatable.get_outermost().get_path_name() == struct_path, "{} != {}".format(struct_from_datatable.get_outermost().get_path_name(), struct_path)
            msgs.append("Struct info.")

            # 7 column name
            self.add_test_log("created_datatable")
            column_names = unreal.PythonDataTableLib.get_column_names(created_datatable, friendly_name=True)
            assert len(column_names) == 5, f"column name count: {len(column_names)} != 5"
            for i, name in enumerate(["my_float_vars", "my_bool_var", "my_transform_var", "my_mesh_var", "name_to_mesh_dict"]):
                if i == 0:
                    self.add_test_log("get_column_name")
                _name = unreal.PythonDataTableLib.get_column_name(created_datatable, i, friendly_name=True)
                assert name == _name, f"column {i}: {_name} != {name}"
            msgs.append("Column name.")

            # 7 shape
            self.add_test_log("created_datatable")
            shape = unreal.PythonDataTableLib.get_shape(created_datatable)
            assert shape == [2, 5], f"shape: {shape} != [2, 5]"
            msgs.append("Shape.")

            # 8 get property
            self.add_test_log("get_property_as_string_at")
            ori_property = unreal.PythonDataTableLib.get_property_as_string_at(created_datatable, row_id=0, column_id=0)
            assert ori_property == "", f"ori_property: != empty"

            # 9 set property
            self.add_test_log("set_property_by_string_at")
            unreal.PythonDataTableLib.set_property_by_string_at(created_datatable, row_index=0, column_index=0, value_as_string='(1.1, 2.2, 3.3)')
            self.add_test_log("set_property_by_string")
            unreal.PythonDataTableLib.set_property_by_string(created_datatable, row_name="MyRow_0", column_name="my_bool_var", value_as_string='True')
            unreal.PythonDataTableLib.set_property_by_string(created_datatable, row_name="MyRow_0",column_name="my_mesh_var"
                                                             , value_as_string="StaticMesh'/Game/StarterContent/Props/SM_TableRound.SM_TableRound'")
            unreal.PythonDataTableLib.set_property_by_string(created_datatable, row_name="MyRow_0", column_name="my_transform_var"
                                                    , value_as_string='(Rotation=(X=0,Y=0,Z=0,W=1),Translation=(X=7,Y=7,Z=7),Scale3D=(X=1,Y=1,Z=1))')

            unreal.PythonDataTableLib.set_property_by_string_at(created_datatable, row_index=1, column_index=1, value_as_string='True')

            self.add_test_log("get_property_as_string_at")
            assert '(1.100000,2.200000,3.300000)' == unreal.PythonDataTableLib.get_property_as_string_at(created_datatable, row_id=0, column_id=0), "value assert failed. @[0][0]"
            self.add_test_log("get_property_as_string_at")
            assert 'True' == unreal.PythonDataTableLib.get_property_as_string_at(created_datatable, row_id=0, column_id=1), "value assert failed. @[0][1]"
            assert 'True' == unreal.PythonDataTableLib.get_property_as_string_at(created_datatable, row_id=1, column_id=1), "value assert failed. @[1][1]"

            assert "StaticMesh'/Game/StarterContent/Props/SM_TableRound.SM_TableRound'" == unreal.PythonDataTableLib.get_property_as_string_at(created_datatable, row_id=0, column_id=3) \
                                      , "value assert failed. @[0][3]: current: {}".format(unreal.PythonDataTableLib.get_property_as_string_at(created_datatable, row_id=0, column_id=3))

            msgs.append("set_property")
            # 10. set dict
            value_str = '(("Chair", StaticMesh\'"/Game/StarterContent/Props/SM_Chair.SM_Chair"\'),("Cube", StaticMesh\'"/Engine/BasicShapes/Cube.Cube"\'))'
            # unreal.PythonDataTableLib.set_property_by_string_at(created_datatable, 1, 5, value_str)
            unreal.PythonDataTableLib.set_property_by_string(created_datatable, row_name="MyRow_1", column_name="name_to_mesh_dict", value_as_string=value_str)
            self.add_test_log("get_property_as_string")
            after_property_str = unreal.PythonDataTableLib.get_property_as_string(created_datatable, row_name="MyRow_1", column_name="name_to_mesh_dict")
            assert value_str == after_property_str, f"value as str not same after set. {value_str} vs {after_property_str}"

            msgs.append("set_property_by_string")
            # 11.
            self.add_test_log("get_table_as_json")
            table_as_json = unreal.PythonDataTableLib.get_table_as_json(created_datatable)
            assert '"Chair": "StaticMesh\'/Game/StarterContent/Props/SM_Chair.SM_Chair\'"' in table_as_json, '"Chair content not in json"'
            msgs.append("get_table_as_json")
            #
            self.add_test_log("duplicate_row")
            unreal.PythonDataTableLib.duplicate_row(created_datatable, "MyRow_1", "DuplicatedRow_2")
            after_duplicate_str = unreal.PythonDataTableLib.get_property_as_string(created_datatable, row_name="DuplicatedRow_2", column_name="name_to_mesh_dict")
            assert value_str == after_duplicate_str, f"value as str not same after duplicate set. {value_str} vs {after_property_str}"
            self.add_test_log("reset_row")
            unreal.PythonDataTableLib.reset_row(created_datatable, "DuplicatedRow_2")

            # 12 flaten
            self.add_test_log("get_flatten_data_table")
            flatten = unreal.PythonDataTableLib.get_flatten_data_table(created_datatable, include_header=True)
            print(flatten)

            unreal.EditorAssetLibrary.save_asset(datatable_path)
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def test_category_datatable(self, id):
        self.test_being(id=id)
        level_path = '/Game/StarterContent/Maps/StarterMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)

        self.push_call(py_task(self._delete_assets, asset_paths=[f"{self.temp_assets_folder}/{x}" for x in ["IAmADataTable", "IAmAStruct", "IAmAEnum"]]
                               ), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_user_defined_enum), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_user_defined_struct), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_user_datatable), delay_seconds=0.1)

        self.test_finish(id)

    def _testcase_prepare_empty_level(self, level_path):
        succ, msgs = False, []
        try:
            # 1. delete if level1 exists.
                # load another level
            unreal.EditorLevelLibrary.load_level('/Game/StarterContent/Maps/StarterMap')
            unreal.PythonBPLib.delete_asset(level_path, show_confirmation=False)


            unreal.EditorLevelLibrary.new_level_from_template(asset_path=level_path, template_asset_path='/Engine/Maps/Templates/Template_Default.Template_Default')
            # 2. open level
            unreal.EditorLevelLibrary.load_level(level_path)
            world = unreal.EditorLevelLibrary.get_editor_world()

            assert world.get_name() == os.path.basename(level_path), f"world name: {world.get_name()} != {os.path.basename(level_path)}"

            # 3. delete ground actor
            if False:
                for actor in unreal.PythonBPLib.find_actors_by_label_name("Floor", world=world):
                    actor.destroy_actor()
            msgs.append("Empty level.")
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_landscape(self):
        succ, msgs = False, []
        try:
            # 0
            section_size = 63
            section_per_component = 2
            component_count_x_y = 1
            Z_HEIGHT_RANGE = 400
            self.add_test_log("create_landscape")
            land_actor = unreal.PythonLandscapeLib.create_landscape(
                landscape_transform=unreal.Transform(location=[0, 0, 0], rotation=[0, 0, 0],
                                                     scale=[100, 100, Z_HEIGHT_RANGE / 512 * 100]
                                                     )
                , section_size=section_size
                , sections_per_component=section_per_component
                , component_count_x=component_count_x_y
                , component_count_y=component_count_x_y
            )
            self.add_test_log("get_landscape_guid")
            guid = unreal.PythonLandscapeLib.get_landscape_guid(land_actor)
            assert guid, "guid == 0"

            unreal.PythonBPLib.select_actor(land_actor, selected=True, notify=True)
            unreal.PythonBPLib.request_viewport_focus_on_selection()
            land_actor.destroy_actor()

            # 1
            half_height = 400_00
            section_size = 255 # meter in scale 100.0

            t = unreal.Transform(location=[-section_size*100, -section_size * 100, half_height], rotation=[0, 0, 0], scale=[100, 100, half_height / 256])
            this_land = unreal.PythonLandscapeLib.create_landscape(t, section_size=section_size
                                                                   , sections_per_component=1
                                                                   , component_count_x=2, component_count_y=2)
            self.add_test_log("cal_landscape_size")
            height_data_size = unreal.PythonLandscapeLib.cal_landscape_size(section_size
                                                                            , sections_per_component=1
                                                                            , component_count_x=2, component_count_y=2)
            print(f"height_data_size: {height_data_size}")
            msgs.append("create landscape")
            # 1. fill height
            assert (511, 511) == height_data_size, f"{height_data_size} != (511, 511)" # 256 *2 -1
            height_data = [0] * height_data_size[0] * height_data_size[1]
            x_count, y_count = height_data_size
            for y in range(y_count):
                for x in range(x_count):
                    index = x + y * x_count
                    # height_data[index] = min(round((x + y) / (x_count-1 + y_count-1) * 65535), 65535)
                    x_v = x / (x_count-1)
                    y_v = y / (y_count-1)
                    v = (math.sqrt(x_v) + math.sqrt(y_v)) * 0.5
                    height_data[index] = min(v * 65535, 65535)
            self.add_test_log("set_heightmap_data")
            unreal.PythonLandscapeLib.set_heightmap_data(this_land, height_data=height_data)

            self.add_test_log("get_heightmap_data")
            heightmap_back = unreal.PythonLandscapeLib.get_heightmap_data(this_land)
            assert heightmap_back == height_data, "heightmap_back != height_data"
            msgs.append("fill heightmap of landscape")
            #
            unreal.PythonBPLib.select_actor(this_land, selected=True, notify=True)
            unreal.PythonBPLib.request_viewport_focus_on_selection()

            # 2. debug draw lines
            half_width = (height_data_size[0] - 1) * 100 * 0.5
            corner_locations = [  unreal.Vector(-half_width, -half_width, 0)
                                , unreal.Vector(half_width, -half_width, half_height)
                                , unreal.Vector(half_width, half_width,  half_height * 2)
                                , unreal.Vector(-half_width, half_width, half_height) ]
            for i in range(4):
                unreal.SystemLibrary.draw_debug_line(unreal.EditorLevelLibrary.get_editor_world()
                                                     , corner_locations[i], corner_locations[(i+1) % 4]
                                                     , unreal.LinearColor.RED, duration=10, thickness=200)
            # 3. comps
            self.add_test_log("get_landscape_components")
            comps = unreal.PythonLandscapeLib.get_landscape_components(this_land)
            assert comps, "landscape comps None"
            assert len(comps) == 4, "landscape comps count != 4"
            msgs.append("landscape comps")

            # 4. grasstype
            grasstype_mat_path= '/Game/_AssetsForTAPythonTestCase/GrassType/Materials/M_Landscape_Grass.M_Landscape_Grass'
            assert unreal.EditorAssetLibrary.does_asset_exist(grasstype_mat_path), "grasstype mat not exists"

            this_land.set_editor_property("landscape_material", unreal.load_asset(grasstype_mat_path))

            # 5. get gresstype components(hism)
            grasstype_mesh_path = '/Engine/BasicShapes/Cylinder'

            self.add_test_log("landscape_flush_grass_components")
            unreal.PythonLandscapeLib.landscape_flush_grass_components(this_land, flush_grass_maps=True)
            self.add_test_log("landscape_update_grass")
            unreal.PythonLandscapeLib.landscape_update_grass(this_land, cameras=[], force_sync=True)
            # 5.1 get grass component from PythonLandscapeLib
            self.add_test_log("landscape_get_grass_components")
            grass_comps = unreal.PythonLandscapeLib.landscape_get_grass_components(this_land)
            assert grass_comps, "get grass components None."
            print(f"grass_comps count {len(grass_comps)}")
            # 5.2 get grass component by class
            hisms = unreal.PythonBPLib.get_objects_by_class(this_land.get_world(), unreal.HierarchicalInstancedStaticMeshComponent)
            assert hisms, "hism Null"
            for comp in grass_comps:
                assert comp in hisms, f"grasstype comp: {comp.get_name()} not in hisms"

            grass_meshes = set()
            for i, hism in enumerate(hisms):
                if hism.static_mesh and isinstance(hism.get_outer(), unreal.LandscapeProxy):
                    grass_meshes.add(hism.static_mesh)
            assert grass_meshes and len(grass_meshes) > 0, "Can't find grasstype mesh"
            for grass_mesh in grass_meshes:
                assert grass_mesh.get_outermost().get_path_name() == grasstype_mesh_path, f"grasstype mesh != {grasstype_mesh_path} "
            msgs.append("Grasstype comps")

            succ = True
        except AssertionError as e:
            msgs.append(str(e))
        self.push_result(succ, msgs)


    def _testcase_landscape_add_adjacent(self):
        succ, msgs = False, []
        try:
            section_size = 63
            section_per_component = 1
            component_count_x_y = 1
            Z_HEIGHT_RANGE = 50
            per_land_offset = section_size * section_per_component * component_count_x_y * 100
            center_land = unreal.PythonLandscapeLib.create_landscape(
                landscape_transform=unreal.Transform(location=[10000, 0, 25 * 100], rotation=[0, 0, 0], # with some offset
                                                     scale=[100, 100, Z_HEIGHT_RANGE / 512 * 100]
                                                     )
                , section_size=section_size
                , sections_per_component=section_per_component
                , component_count_x=component_count_x_y
                , component_count_y=component_count_x_y
            )

            x_postive, x_nagetive = 0, 2
            y_positve, y_nagetive = 1, 3

            world = center_land.get_world()
            # add cross
            #   ---> X
            # | 0, 1, 2
            # | 3, c, 5
            # | 6, 7, 8
            # +y
            self.add_test_log("add_adjacent_landscape_proxy")
            land_5 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, center_land, x_postive)
            land_7 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, center_land, y_positve)
            land_3 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, center_land, x_nagetive)
            land_1 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, center_land, y_nagetive)

            land_2 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, land_5, y_nagetive)
            land_8 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, land_5, y_positve)

            land_0 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, land_3, y_nagetive)
            land_6 = unreal.PythonLandscapeLib.add_adjacent_landscape_proxy(world, land_3, y_positve)

            lands = [ land_0, land_1, land_2
                    , land_3, center_land, land_5
                    , land_6, land_7, land_8 ]


            # todo, fill height maps, focus

            # heightmap: all heightmap data with 3x3 landscape
            self.add_test_log("get_heightmap_data")
            heightmap = unreal.PythonLandscapeLib.get_heightmap_data(center_land)
            assert heightmap, "heightmap None"
            assert len(heightmap) == (3 * 63 + 1) * (3 * 63 + 1), f"heightmap: {len(heightmap)}"
            print(f"heightmap_back: {len(heightmap)}")
            width = height = (3 * section_size + 1)

            for tile_y in range(3):
                for tile_x in range(3):
                    resolution_size = section_size * section_per_component * component_count_x_y + 1
                    x_offset = tile_x * (resolution_size-1)  # landscape share 1 edge with neighbour landscape
                    y_offset = tile_y * (resolution_size-1)

                    per_proxy_height = [0] *(resolution_size*resolution_size)
                    for y in range(64):
                        for x in range(64):
                            _x = x + x_offset
                            _y = y + y_offset
                            v_x = math.sin(_x / 10.0) * 0.5 + 0.5
                            v_y = math.sin(_y / 15.0) * 0.5 + 0.5
                            v = min(max(v_x, v_y), 1)
                            index = x + y * resolution_size
                            per_proxy_height[index] = (1-v) * 0.5 * 65535
                    unreal.PythonLandscapeLib.set_heightmap_data(lands[tile_x + tile_y *3], per_proxy_height)

            print("after set heigth map")

            unreal.PythonBPLib.select_none()
            for land in lands:
                unreal.PythonBPLib.select_actor(land, selected=True, notify=True)
            unreal.PythonBPLib.request_viewport_focus_on_selection()
            unreal.PythonBPLib.select_none()

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_landscape_proxy(self):
        succ, msgs = False, []
        section_size = 31
        section_per_component = 2
        component_count_x_y = 2
        Z_HEIGHT_RANGE = 100
        per_land_offset = section_size * section_per_component * component_count_x_y * 100
        assert per_land_offset == 12400, f"per_land_offset: {per_land_offset} != 12400"

        try:
            global_x_offset = 100_00
            center_land_t = unreal.Transform(location=[global_x_offset, 0, 0], rotation=[0, 0, 0], scale=[100, 100, Z_HEIGHT_RANGE / 512 * 100])
            center_land = unreal.PythonLandscapeLib.create_landscape(landscape_transform=center_land_t
                                            , section_size=section_size
                                            , sections_per_component=section_per_component
                                            , component_count_x=component_count_x_y
                                            , component_count_y=component_count_x_y)

            guid = unreal.PythonLandscapeLib.get_landscape_guid(center_land)
            assert unreal.GuidLibrary.invalidate_guid(guid), "invalidate guid"

            lands = []
            for y in range(-1, 2):  # -1, 0, 1
                for x in range(-1, 2): # -1, 0, 1
                    if x == 0 and y == 0:
                        comps = unreal.PythonLandscapeLib.get_landscape_components(center_land)
                        assert len(comps) == component_count_x_y * component_count_x_y, f"land comp count: {len(comps)} error "
                        lands.append(center_land)
                        continue    # center landscape, created already
                    x_pos = per_land_offset * x + global_x_offset
                    y_pos = per_land_offset * y
                    x1_t = unreal.Transform(location=[x_pos, y_pos, 0], rotation=[0, 0, 0], scale=[100, 100, Z_HEIGHT_RANGE / 512 * 100])
                    if y == -1 and x == -1:
                        self.add_test_log("create_landscape_proxy")
                    this_land = unreal.PythonLandscapeLib.create_landscape_proxy(landscape_transform=x1_t
                                                    , section_size=section_size
                                                    , sections_per_component=section_per_component
                                                    , component_count_x=component_count_x_y
                                                    , component_count_y=component_count_x_y
                                                    , shared_landscape_actor=center_land)
                    lands.append(this_land)
            # set heightmap
            for tile_y in range(-1, 2):  # -1, 0, 1
                for tile_x in range(-1, 2):  # -1, 0, 1
                    resolution_size = section_size * section_per_component *component_count_x_y + 1
                    x_offset = tile_x * (resolution_size - 1)  # landscape share 1 edge with neighbour landscape
                    y_offset = tile_y * (resolution_size - 1)

                    per_proxy_height = [0] *(resolution_size * resolution_size)
                    for y in range(resolution_size):
                        for x in range(resolution_size):
                            _x = x + x_offset
                            _y = y + y_offset
                            v_x = math.sin(_x / 10.0) * 0.5 + 0.5
                            v_y = math.sin(_y / 15.0) * 0.5 + 0.5
                            v = min(max(v_x, v_y), 1)
                            index = x + y * resolution_size
                            per_proxy_height[index] = (1-v) * 0.5 * 65535
                    unreal.PythonLandscapeLib.set_heightmap_data(lands[tile_x + tile_y *3], per_proxy_height)

            unreal.PythonBPLib.select_none()
            for land in lands:
                unreal.PythonBPLib.select_actor(land, selected=True, notify=True)
            unreal.PythonBPLib.request_viewport_focus_on_selection()
            unreal.PythonBPLib.select_none()

            succ = True
        except AssertionError as e:
            msgs.append(e)


        self.push_result(succ, msgs)

    def _testcase_landscape_proxy_with_guid(self):
        succ, msgs = False, []
        try:
            guid = unreal.GuidLibrary.new_guid()
            section_size = 127
            section_per_component = 2
            component_count_x_y = 2
            Z_HEIGHT_RANGE = 100
            per_land_offset = section_size * section_per_component * component_count_x_y * 100
            assert per_land_offset == 50800, f"per_land_offset: {per_land_offset} != 50800"

            global_height_offset = 50_00
            proxies = []
            for y in range(2):
                for x in range(2):
                    this_land_t = unreal.Transform(location=[per_land_offset * x, per_land_offset * y, global_height_offset]
                                                   , rotation=[0, 0, 0]
                                                   , scale=[100, 100, Z_HEIGHT_RANGE / 512 * 100])
                    if x == 0 and y == 0:
                        self.add_test_log("create_landscape_proxy_with_guid")
                    proxy = unreal.PythonLandscapeLib.create_landscape_proxy_with_guid( landscape_transform = this_land_t
                                                        , section_size=section_size
                                                        , sections_per_component=section_per_component
                                                        , component_count_x=component_count_x_y
                                                        , component_count_y=component_count_x_y
                                                        , guid=guid)
                    proxies.append(proxy)
                    assert proxy, "Create landscape proxy failed."

            # heightmap
            for tile_y in range(2):
                for tile_x in range(2):
                    resolution_size = section_size * section_per_component *component_count_x_y + 1
                    x_offset = tile_x * (resolution_size - 1)  # landscape share 1 edge with neighbour landscape
                    y_offset = tile_y * (resolution_size - 1)

                    per_proxy_height = [0] *(resolution_size * resolution_size)
                    for y in range(resolution_size):
                        for x in range(resolution_size):
                            _x = x + x_offset
                            _y = y + y_offset
                            v_x = math.sin(_x / 10.0) * 0.5 + 0.5
                            v_y = math.sin(_y / 15.0) * 0.5 + 0.5
                            scale = math.sin((_x + _y) / 40.0) * 0.5 + 0.5
                            v = min(max(v_x, v_y), 1) * scale
                            index = x + y * resolution_size
                            per_proxy_height[index] = (1-v) * 0.5 * 65535
                    unreal.PythonLandscapeLib.set_heightmap_data(proxies[tile_x + tile_y * 2], per_proxy_height)

            # view
            unreal.PythonBPLib.select_actor(None, selected=False, notify=True)
            unreal.PythonBPLib.select_actor(proxies[-1], selected=True, notify=True)
            unreal.PythonBPLib.request_viewport_focus_on_selection()
            # unreal.PythonBPLib.select_actor(None, selected=False, notify=True)

            succ = True

        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_sub_levels(self):
        succ, msgs = False, []
        world = unreal.EditorLevelLibrary.get_editor_world()
        self.add_test_log("enable_world_composition")
        unreal.PythonBPLib.enable_world_composition(world, enable=True)
        self.add_test_log("get_levels")
        levels = unreal.PythonLevelLib.get_levels(world)
        print(f'levels count: {len(levels)}')

        self.push_result(succ, msgs)

    def _testcast_sub_levels(self):
        world = unreal.EditorLevelLibrary.get_editor_world()
        # unreal.PythonBPLib.enable_world_composition(world, True)
        succ, msgs = False, []
        for tile_y in range(2):
            for tile_x in range(2):
                tile_map_name = f"Sub_x{tile_x:02}_y{tile_y:02}"
                if tile_x == 0 and tile_y == 0:
                    self.add_test_log("add_level_to_world")
                level = unreal.EditorLevelUtils.add_level_to_world(world, tile_map_name, unreal.LevelStreamingDynamic)
                break

        levels = unreal.PythonLevelLib.get_levels(world)
        print(f"levels: {len(levels)}")
        for level in levels:
            print(level.get_name())
        assert(len(levels) == 5), f"level count: {len(levels)} != 5" # 1 + 4

        self.push_result(succ, msgs)

    def _testcase_streaming_levels(self):
        succ, msgs = False, []
        try:
            unreal.EditorLevelLibrary.load_level('/Game/_AssetsForTAPythonTestCase/Maps/OpenWorld/LandscapeProxyMap')
            # 1. add streaming level
            currentWorld = unreal.EditorLevelLibrary.get_editor_world()
            self.add_test_log("get_levels")
            current_level_names = [level.get_outermost().get_name() for level in unreal.PythonLevelLib.get_levels(currentWorld)]
            assert len(current_level_names) == 1, f"current_level count: {len(current_level_names)} != 1"
            sub_level_paths = []
            for y in range(2):
                for x in range(2):
                    level_package_name = f"/Game/_AssetsForTAPythonTestCase/Maps/OpenWorld/Sub_x{x:02}_y{y:02}"
                    sub_level_paths.append(level_package_name)

                    if level_package_name in current_level_names:
                        continue

                    currentWorld = unreal.EditorLevelLibrary.get_editor_world()

                    addedLevel = unreal.EditorLevelUtils.add_level_to_world(currentWorld, level_package_name, unreal.LevelStreamingDynamic)

                    if not addedLevel:
                        unreal.log_warning("Tile map: {}_{}_LOD{} not eixsts, create first")
                    else:
                        print('added level: {}_{}_LOD{}')
            assert len(unreal.PythonLevelLib.get_levels(currentWorld)) == 5, f"level count: {len(unreal.PythonLevelLib.get_levels(currentWorld))} != 5"  # 1 + 4
            # 2. remove streaming level
            for i, level_path in enumerate(sub_level_paths):
                shortLevelName = level_path[level_path.rfind('/') + 1:]
                if i == 0:
                    self.add_test_log("remove_level_from_world")
                unreal.PythonLevelLib.remove_level_from_world(shortLevelName)
            assert len(unreal.PythonLevelLib.get_levels(currentWorld)) == 1, f"level count: {len(unreal.PythonLevelLib.get_levels(currentWorld))} != 1, after remove levels"  # 1

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def test_category_Landscape(self, id):
        self.test_being(id=id)

        self.push_call(py_task(self._testcase_prepare_empty_level, level_path='/Game/_AssetsForTAPythonTestCase/Maps/LandscapeMap'), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_landscape), delay_seconds=1)

        self.push_call(py_task(self._testcase_prepare_empty_level, level_path='/Game/_AssetsForTAPythonTestCase/Maps/OpenWorld/LandscapeProxyMap'), delay_seconds=1)
        self.push_call(py_task(self._testcase_landscape_add_adjacent), delay_seconds=1)
        #
        self.push_call(py_task(self._testcase_prepare_empty_level, level_path='/Game/_AssetsForTAPythonTestCase/Maps/OpenWorld/LandscapeProxyMap'), delay_seconds=1)
        self.push_call(py_task(self._testcase_landscape_proxy), delay_seconds=1)
        #
        self.push_call(py_task(self._testcase_prepare_empty_level, level_path='/Game/_AssetsForTAPythonTestCase/Maps/OpenWorld/LandscapeProxyMap'), delay_seconds=1)
        self.push_call(py_task(self._testcase_landscape_proxy_with_guid), delay_seconds=1)
        #
        self.push_call(py_task(self._testcase_streaming_levels), delay_seconds=3)

        # level_path = '/Game/StarterContent/Maps/StarterMap' # avoid saving level by mistake
        # self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)

        self.test_finish(id)

    def _testcase_texture(self):
        succ, msgs = False, []
        try:
            width = 256
            height = 16
            data = []
            scale = 255/16.0
            channel_num = 3
            for y in range(height):
                for x in range(width):
                    r = round((x % 16) * scale)
                    g = round(y * scale)
                    b = round(round(x / 16) * scale)
                    data.append(r)
                    data.append(g)
                    data.append(b)
            raw_data = bytes(data)
            assert len(raw_data) == width* height * channel_num, f"len(raw_data) size assert failed: {len(raw_data)}"

            # 1. create a transient texture
            self.add_test_log("create_texture2d_from_raw")
            tex = unreal.PythonTextureLib.create_texture2d_from_raw(raw_data=raw_data, width=width, height=height
                        , channel_num=channel_num, use_srgb=False, texture_filter_value=2, bgr=False)
            unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets([tex])
            self.temp_asset = tex

            assert tex, "created texture null"
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_close_temp_assets_editor(self):
        succ, msg = False, ""
        if self.temp_asset:
            unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(self.temp_asset)
        succ = True
        self.push_result(succ, msg)

    def _testcase_create_rt(self):
        succ, msgs = False, []
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

        try:
            folder = "/Game/_AssetsForTAPythonTestCase/Textures"
            rt_name = "RT_Created"
            rt_path = f"{folder}/{rt_name}"
            if unreal.EditorAssetLibrary.does_asset_exist(rt_path):

                unreal.PythonBPLib.delete_asset(rt_path, show_confirmation=False)
            factory = unreal.TextureRenderTargetFactoryNew()
            rt_assets = asset_tools.create_asset(rt_name, folder, unreal.TextureRenderTarget2D, factory)
            print(f"rt_assets.get_path_name: {rt_assets.get_path_name()}")
            rt_assets.set_editor_property("render_target_format", unreal.TextureRenderTargetFormat.RTF_RGBA8)
            unreal.EditorAssetLibrary.save_asset(rt_assets.get_path_name())
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_set_rt(self):
        succ, msgs = False, []
        try:
            folder = "/Game/_AssetsForTAPythonTestCase/Textures"
            rt_name = "RT_Created"
            rt_path = f"{folder}/{rt_name}"
            assert unreal.EditorAssetLibrary.does_asset_exist(rt_path), f"Asset not exist: {rt_path}"
            rt = unreal.load_asset(rt_path)

            assert rt, "rt null"
            self.add_test_log("get_render_target_raw_data")
            raw_data = unreal.PythonTextureLib.get_render_target_raw_data(rt)
            assert raw_data, "get_render_target_raw_data None"
            print(len(raw_data))

            width = rt.get_editor_property("size_x")
            height = rt.get_editor_property("size_y")
            # rgba8
            assert len(raw_data) == width * height * 4 * 1, f"len(raw_data): {len(raw_data)} != width * height * 4"
            # 2
            # bgra order
            raw_data = b'\xff\xff\xff'  # white
            raw_data += b'\x00\x00\x00'  # black
            raw_data += b'\x00\x00\xff'  # red
            raw_data += b'\x00\xff\x00'  # green
            # set rt with smaller "raw_data"
            self.add_test_log("set_render_target_data")
            unreal.PythonTextureLib.set_render_target_data(rt, raw_data
                                                           , raw_data_width=2
                                                           , raw_data_height=2
                                                           , raw_data_channel_num= 3
                                                           , use_srgb = False
                                                           , texture_filter_value=2
                                                           , bgr=True)
            unreal.EditorAssetLibrary.save_asset(rt_path)
            # get raw_data after set
            rt = unreal.load_asset(rt_path)

            # the return raw_data data's pixel is bgra, which is fixed
            self.add_test_log("get_render_target_raw_data")
            raw_data = unreal.PythonTextureLib.get_render_target_raw_data(rt)
            assert len(raw_data) == width * height * 4, f"len(raw_data): {len(raw_data)} != width * height * 4 "

            first_pixel = struct.unpack('BBBB', bytes(raw_data[:4]))
            last_pixel = struct.unpack('BBBB', bytes(raw_data[-4:]))
            # print(f"firstPixel: {first_pixel[0]}, {first_pixel[1]}, {first_pixel[2]}, {first_pixel[3]}" )
            # print(f"lastPixel: {last_pixel[0]}, {last_pixel[1]}, {last_pixel[2]}, {last_pixel[3]}")
            assert first_pixel == (0, 0, 255, 255) , f"first pixel not red, {type(first_pixel)}, {first_pixel}"
            assert last_pixel == (0, 0, 0, 255), "last pixel not black"
            unreal.PythonBPLib.sync_to_assets([unreal.EditorAssetLibrary.find_asset_data(rt_path)])

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_create_swtich_materials(self):
        succ, msgs = False, []
        mat_paths = ["/Game/_AssetsForTAPythonTestCase/Materials/M_StaticSwitch"
            , "/Game/_AssetsForTAPythonTestCase/Materials/MI_StaticSwitch_A"
            , "/Game/_AssetsForTAPythonTestCase/Materials/MI_StaticSwitch_B"
            , "/Game/_AssetsForTAPythonTestCase/Materials/MI_StaticSwitch_C" ]
        # delte exists
        for _path in reversed(mat_paths): # delete mi first
            if unreal.EditorAssetLibrary.does_asset_exist(_path):
                unreal.EditorAssetLibrary.save_asset(_path)
                unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(unreal.load_asset(_path))

                unreal.PythonBPLib.delete_asset(_path, show_confirmation=False)
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        try:
            # create m
            m_path = mat_paths[0]

            mat_name = os.path.basename(m_path)
            folder_name = os.path.dirname(m_path)

            mat = asset_tools.create_asset(mat_name, folder_name, unreal.Material, unreal.MaterialFactoryNew())
            self.add_test_log("get_shader_map_info")
            map_infos = unreal.PythonMaterialLib.get_shader_map_info(mat, "PCD3D_SM5")
            assert map_infos, "map_info null"
            print(map_infos)
            assert '"ShaderMapName"' in map_infos, "Can't find ShaderID.VFType"

            self.add_test_log("create_material_expression")
            switch_force_blue = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionStaticSwitchParameter)
            switch_force_blue.set_editor_property("parameter_name", "ForceUseBlue")
            switch_use_red = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionStaticSwitchParameter)
            switch_use_red.set_editor_property("parameter_name", "UseRed")

            c_blue = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVectorParameter)
            c_blue.set_editor_property("default_value", unreal.LinearColor.BLUE)
            c_blue.set_editor_property("parameter_name", "Blue")

            c_red = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVectorParameter)
            c_red.set_editor_property("default_value", unreal.LinearColor.RED)
            c_red.set_editor_property("parameter_name", "Red")

            c_green = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVectorParameter)
            c_green.set_editor_property("default_value", unreal.LinearColor.GREEN)
            c_green.set_editor_property("parameter_name", "Green")

            # offical lib: MaterialEditingLibrary
            unreal.MaterialEditingLibrary.connect_material_property(from_expression=switch_force_blue, from_output_name=""
                                                               , property_=unreal.MaterialProperty.MP_BASE_COLOR)
            # MP_WorldPositionOffset connection will be disconnect later
            self.add_test_log("connect_material_property")
            unreal.PythonMaterialLib.connect_material_property(from_expression=switch_force_blue, from_output_name=""
                                                               , material_property_str="MP_WorldPositionOffset")

            # swith a
            unreal.MaterialEditingLibrary.connect_material_expressions(from_expression=c_blue, from_output_name=""
                                                                       , to_expression=switch_force_blue, to_input_name="True")

            unreal.MaterialEditingLibrary.connect_material_expressions(from_expression=switch_use_red, from_output_name=""
                                                                   , to_expression=switch_force_blue, to_input_name="False")
            # PythonMaterialLib way, add extra log when failed.
            self.add_test_log("connect_material_expressions")
            unreal.PythonMaterialLib.connect_material_expressions(from_expression=c_red, from_output_name=""
                                                                       , to_expression=switch_use_red, to_input_name="True")
            unreal.PythonMaterialLib.connect_material_expressions(from_expression=c_green, from_output_name=""
                                                                       , to_expression=switch_use_red, to_input_name="False")

            unreal.MaterialEditingLibrary.layout_material_expressions(mat)
            unreal.MaterialEditingLibrary.recompile_material(mat)
            unreal.EditorAssetLibrary.save_asset(mat.get_path_name())

            self.add_test_log("get_hlsl_code")
            hlsl = unreal.PythonMaterialLib.get_hlsl_code(mat)

            msgs.append("Create Material.")

            unreal.PythonBPLib.sync_to_assets([unreal.EditorAssetLibrary.find_asset_data(m_path)]
                                              , allow_locked_browsers=True, focus_content_browser=True)

            # 3. create mis
            assert mat and isinstance(mat, unreal.Material), "mat None or type error"
            for i, mi_path in enumerate(mat_paths[1:]):
                mi_name = os.path.basename(mi_path)
                folder_name = os.path.dirname(mi_path)
                mi = asset_tools.create_asset(mi_name, folder_name, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
                unreal.MaterialEditingLibrary.set_material_instance_parent(mi, mat)
                if i == 0:
                    self.add_test_log("set_static_switch_parameter_value")
                    unreal.PythonMaterialLib.set_static_switch_parameter_value(mi, "UseRed", enabled=True, update_static_permutation=True)
                elif i == 1:
                    self.add_test_log("set_static_switch_parameters_values")
                    unreal.PythonMaterialLib.set_static_switch_parameters_values(mi, switch_names=["UseRed", "ForceUseBlue"]
                                                                                 , values=[False, False], overrides=[True, True])
                elif i == 2:
                    unreal.PythonMaterialLib.set_static_switch_parameter_value(mi, "ForceUseBlue", enabled=True, update_static_permutation=True)

                unreal.EditorAssetLibrary.save_asset(mi_path)
                msgs.append(f"Creaste MI: {mi.get_name()}")
            mat = None
            assert hlsl, "hlsl None"

            # 4. get_static_switch_parameter_values
            assert os.path.basename(mat_paths[1]).startswith("MI_"), "not mi"
            mi = unreal.load_asset(mat_paths[1])
            assert mi, "mi None"

            self.add_test_log("get_static_switch_parameter_values")
            switchs_value = unreal.PythonMaterialLib.get_static_switch_parameter_values(mi)
            assert switchs_value and switchs_value == [{"name": "UseRed", "value": True, "override": True}], f"switchs_value assert failed: {switchs_value}"
            msgs.append("Static switch parameter.")

            # 5. get_static_parameters_summary will be Deprecated in next
            self.add_test_log("get_static_parameters_summary")
            swith_counts, switch_types_str = unreal.PythonMaterialLib.get_static_parameters_summary(mi)
            print(f"swith_counts_str: {swith_counts}, type: {type(swith_counts)}")
            print(f"switch_types_str: {switch_types_str}, type: {type(switch_types_str)}")

            self.add_test_log("get_unreal_version")
            engine_version = unreal.PythonBPLib.get_unreal_version()
            if engine_version['major'] == 5:
                assert swith_counts == [1, 0, 0, 0], f"swith_counts_str: {swith_counts} != [1, 0, 0, 0]"
            else:
                assert swith_counts == [1, 0, 0, 0, 0], f"swith_counts_str: {swith_counts} != [1, 0, 0, 0, 0]"
            # 6. log_mat

            mat = unreal.load_asset(m_path)
            unreal.PythonTestLib.clear_log_buffer()
            self.add_test_log("log_mat")
            unreal.PythonMaterialLib.log_mat(mat)
            logs = unreal.PythonTestLib.get_logs(category_regex="PythonTA")
            assert logs, "Logs None"
            assert list(filter(lambda o: "[4]       [2] Switch Param (False)/'UseRed'.False <--  Param (0,1,0,1)/'Green'" in o, logs)), "Can't find material switch info in logs"
            msgs.append("get_logs")
            # 7. material content
            self.add_test_log("get_material_content")
            material_in_json = unreal.PythonMaterialLib.get_material_content(mat, only_editable=True, include_comments=False)
            json_obj = json.loads(material_in_json)
            assert len(json_obj) >= 4, "Json object from material length assert failed"

            # 8. set_shading_model
            ori_shading_model = mat.get_editor_property("shading_model")
            self.add_test_log("set_shading_model")
            unreal.PythonMaterialLib.set_shading_model(mat, 2)  #2.  MSM_Subsurface, 12.  MSM_Strata hidden in 5.0.3 and will crash after set.
            after_shading_model = mat.get_editor_property("shading_model")
            assert after_shading_model == unreal.MaterialShadingModel.MSM_SUBSURFACE, f"after_shading_model {after_shading_model} != unreal.MaterialShadingModel.MSM_SUBSURFACE"
            mat.set_editor_property("shading_model", ori_shading_model) # set back

            # 9. expression
            self.add_test_log("get_material_expressions")
            expressions = unreal.PythonMaterialLib.get_material_expressions(mat)
            assert expressions, "expressions none"
            assert len(expressions) == 5, f"expression count: {len(expressions)} != 5" # 2 switches, 3 Vector
            # 9.1. connections
            self.add_test_log("get_material_connections")
            connections = unreal.PythonMaterialLib.get_material_connections(mat)
            assert connections, "connections null"
            assert len(connections) == 6, f"len(connections): {len(connections)} != 6 "

            self.add_test_log("disconnect_material_property")
            unreal.PythonMaterialLib.disconnect_material_property(mat, "MP_WorldPositionOffset")
            connections = unreal.PythonMaterialLib.get_material_connections(mat)
            assert len(connections) == 5, f"len(connections): {len(connections)} != 5, after disconnection "

            # 9.2
            exp_0 = expressions[0]
            assert isinstance(exp_0, unreal.MaterialExpressionStaticSwitchParameter), "exp_0 is not MaterialExpressionStaticSwitchParameter"
            self.add_test_log("get_material_expression_input_names")
            input_names = unreal.PythonMaterialLib.get_material_expression_input_names(exp_0)
            assert input_names == ["True", "False"], "input_names != ['True', 'False']"
            msgs.append("get_material_expression_input_names")

            self.add_test_log("get_material_expression_output_names")
            output_names = unreal.PythonMaterialLib.get_material_expression_output_names(exp_0)
            assert output_names == ["None"], "output_names != ['None']"
            msgs.append("get_material_expression_output_names")

            self.add_test_log("get_material_expression_captions")
            captions = unreal.PythonMaterialLib.get_material_expression_captions(exp_0)
            assert captions == ["Switch Param (False)", "\'ForceUseBlue\'"], f"Captions assert failed.: {captions}, type: {type(captions)}"
            msgs.append("get_material_expression_captions")

            self.add_test_log("get_material_expression_id")
            guid = unreal.PythonMaterialLib.get_material_expression_id(exp_0)
            assert guid, "guid None"
            assert isinstance(guid, unreal.Guid), "guid type assert failed."
            self.add_test_log("guid_from_string")
            generated_guid = unreal.PythonBPLib.guid_from_string(guid.to_string())

            assert unreal.GuidLibrary.equal_equal_guid_guid(guid, generated_guid), f"guid: {guid.to_string()} != generated guid: {generated_guid.to_string()}"
            # GuidLibrary.equal_equal_guid_guid, funny name
            msgs.append("get_material_expression_id")

            unreal.PythonTestLib.clear_log_buffer()
            self.add_test_log("log_material_expression")
            unreal.PythonMaterialLib.log_material_expression(exp_0)
            logs = unreal.PythonTestLib.get_logs(category_regex="PythonTA")
            assert len(logs) == 6, f"logs count: {len(logs)} != 6"


            # 9.3
            unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(mat)

            unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets([mat])
            self.add_test_log("get_selected_material_nodes")
            selected_exps = unreal.PythonMaterialLib.get_selected_material_nodes(mat)
            assert len(selected_exps) == 0, "assert selected_exps count failed" # use in material editor
            # another similar function
            self.add_test_log("get_selected_nodes_in_material_editor")
            selected = unreal.PythonMaterialLib.get_selected_nodes_in_material_editor(mat)
            assert len(selected_exps) == 0, "assert selected_exps count failed, get_selected_nodes_in_material_editor"

            # 9.4
            unreal.PythonTestLib.clear_log_buffer()
            self.add_test_log("log_editing_nodes")
            unreal.PythonMaterialLib.log_editing_nodes(mat)
            logs = unreal.PythonTestLib.get_logs()
            assert list(filter(lambda o: "PythonTA: Editing Material: M_StaticSwitch" in o, logs)), "log_editing_nodes failed."
            msgs.append("get_material_expression_id")

            unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(mat)
            msgs.append("get_selected_material_nodes")
            # 10.1
            mat_path = "/Game/_AssetsForTAPythonTestCase/Materials/M_FeatureLevel4Test"
            if not unreal.EditorAssetLibrary.does_asset_exist(mat_path):
                folder, mat_name = mat_path.rsplit("/", 1)
                mat = asset_tools.create_asset(mat_name, folder, unreal.Material, unreal.MaterialFactoryNew())
                unreal.EditorAssetLibrary.save_asset(mat.get_path_name())

                exp_feature = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionFeatureLevelSwitch)

                exp_add = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionAdd)
                exp_one = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant)
                exp_one.set_editor_property("r", 1)
                exp_zero = unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant)
                exp_zero.set_editor_property("r", 0)

                esp_sm31 = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVectorParameter)
                esp_sm31.set_editor_property("parameter_name", "ES31")
                esp_sm31.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))

                unreal.MaterialEditingLibrary.connect_material_property(from_expression=exp_feature, from_output_name=""
                                                                    , property_=unreal.MaterialProperty.MP_BASE_COLOR)
                self.add_test_log("connect_material_expressions")
                unreal.PythonMaterialLib.connect_material_expressions(exp_one, "", exp_add, "A")
                unreal.PythonMaterialLib.connect_material_expressions(exp_zero, "", exp_add, "B")

                unreal.PythonMaterialLib.connect_material_expressions(exp_add, "", exp_feature, "DEFAULT")
                unreal.PythonMaterialLib.connect_material_expressions(esp_sm31, "", exp_feature, "ES3_1")

                unreal.MaterialEditingLibrary.layout_material_expressions(mat)
                unreal.EditorAssetLibrary.save_asset(mat.get_path_name())


            # 10.2 get_all_referenced_expressions
            mat_feature_level = unreal.load_asset('/Game/_AssetsForTAPythonTestCase/Materials/M_FeatureLevel4Test')
            self.add_test_log("get_all_referenced_expressions")
            expressions = unreal.PythonMaterialLib.get_all_referenced_expressions(mat_feature_level, feature_level=3) #SM5
            expressions_es31 = unreal.PythonMaterialLib.get_all_referenced_expressions(mat_feature_level, feature_level=1) #SM5
            assert len(expressions) == 4, f"M_FeatureLevel4Test len(expressions): {len(expressions)} != 4"
            assert len(expressions_es31) == 2, f"len(expressions_es31): {len(expressions_es31)} != 2"
            msgs.append("get_all_referenced_expressions")

            # 11.
            self.add_test_log("gen_guid_from_material_property_str")
            guid = unreal.PythonMaterialLib.gen_guid_from_material_property_str("MP_BaseColor")
            self.add_test_log("get_material_proper_str_from_guid")
            name = unreal.PythonMaterialLib.get_material_proper_str_from_guid(guid)
            assert name == "MP_BaseColor", f"name: {name} != 'MP_BaseColor'"
            guid = unreal.PythonMaterialLib.gen_guid_from_material_property_str("MP_CustomData0")
            name = unreal.PythonMaterialLib.get_material_proper_str_from_guid(guid)
            assert name == "MP_CustomData0", f"name: {name} != 'MP_CustomData0'"
            msgs.append("gen_guid_from_material_property_str / get_material_proper_str_from_guid")

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_material_attributes(self):
        succ, msgs = False, []
        try:
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            mat_paths = ["/Game/_AssetsForTAPythonTestCase/Materials/M_Attributes"]
            # 1. delte exists
            for _path in reversed(mat_paths): # delete mi first
                if unreal.EditorAssetLibrary.does_asset_exist(_path):
                    unreal.EditorAssetLibrary.save_asset(_path)
                    unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(unreal.load_asset(_path))
                    unreal.PythonBPLib.delete_asset(_path, show_confirmation=False)
            # 2. create a new
            mat_path = mat_paths[0]
            folder, mat_name = mat_path.rsplit("/", 1)
            mat = asset_tools.create_asset(mat_name, folder, unreal.Material, unreal.MaterialFactoryNew())
            unreal.EditorAssetLibrary.save_asset(mat.get_path_name())


            # 2.1 MaterialExpressionSetMaterialAttributes
            node_sma = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionSetMaterialAttributes,
                                                                                node_pos_x=-500, node_pos_y=0)
            property_names = ["MP_Specular", "MP_Normal", "MP_WorldPositionOffset", "MP_CustomData0"]

            self.add_test_log("add_input_at_expression_set_material_attributes")
            for mp_name in property_names:
                unreal.PythonMaterialLib.add_input_at_expression_set_material_attributes(node_sma, mp_name)

            # same with MaterialExpressionGetMaterialAttributes
            node_gma = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionGetMaterialAttributes,
                                                                                node_pos_x=-200, node_pos_y=0)
            self.add_test_log("add_output_at_expression_get_material_attributes")
            for mp_name in property_names:
                unreal.PythonMaterialLib.add_output_at_expression_get_material_attributes(node_gma, mp_name)
            unreal.PythonMaterialLib.connect_material_expressions(from_expression=node_sma, from_output_name=""
                                                                  , to_expression=node_gma, to_input_name="")

            for mp_name in property_names:
                unreal.PythonMaterialLib.connect_material_property(node_gma, mp_name, mp_name)

            switch_spec = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionStaticSwitchParameter)
            switch_spec.set_editor_property("parameter_name", "SpecUseOne")

            exp_spec = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVectorParameter)
            exp_spec.set_editor_property("parameter_name", "Zero")

            exp_spec_one = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVectorParameter)
            exp_spec_one.set_editor_property("parameter_name", "One")
            exp_spec_one.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))

            unreal.PythonMaterialLib.connect_material_expressions(exp_spec_one, "", switch_spec, "True")
            unreal.PythonMaterialLib.connect_material_expressions(exp_spec, "", switch_spec, "False")

            esp_normal = unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
            esp_normal.set_editor_property("parameter_name", "Normal")
            esp_normal.set_editor_property("default_value", unreal.LinearColor(0, 0, 1, 0))
            esp_wpo = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVectorParameter)
            esp_wpo.set_editor_property("parameter_name", "WPO")
            esp_cd0 = unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant2Vector)
            # esp_cd0.set_editor_property("parameter_name", "CustomData0")

            for mp_name, express in zip(["Specular", "Normal", "World Position Offset", "Custom Data 0"], [switch_spec, esp_normal, esp_wpo, esp_cd0]):
                # unreal.PythonMaterialLib.connect_material_property(node_gma, mp_name, mp_name)
                unreal.PythonMaterialLib.connect_material_expressions(express, "", node_sma, mp_name)

            unreal.MaterialEditingLibrary.layout_material_expressions(mat)
            unreal.EditorAssetLibrary.save_asset(mat_path)

            # 3. create MF
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            mf_path = "/Game/_AssetsForTAPythonTestCase/Materials/MF_ForTestCase"

            if unreal.EditorAssetLibrary.does_asset_exist(mf_path):
                # delete first
                unreal.EditorAssetLibrary.save_asset(mf_path)
                unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(unreal.load_asset(mf_path))
                unreal.PythonBPLib.delete_asset(mf_path, show_confirmation=False)

            folder, mf_name = mf_path.rsplit("/", 1)

            my_mf = asset_tools.create_asset(mf_name, folder, unreal.MaterialFunction, unreal.MaterialFunctionFactoryNew())

            unreal.EditorAssetLibrary.save_asset(mf_path)
            output_node = unreal.MaterialEditingLibrary.create_material_expression_in_function(my_mf, unreal.MaterialExpressionFunctionOutput)

            esp_switch = unreal.MaterialEditingLibrary.create_material_expression_in_function(my_mf, unreal.MaterialExpressionStaticSwitchParameter)
            esp_switch.set_editor_property("parameter_name", "UseOne")

            exp_spec_zero = unreal.MaterialEditingLibrary.create_material_expression_in_function(my_mf, unreal.MaterialExpressionVectorParameter)
            exp_spec_zero.set_editor_property("parameter_name", "Zero")

            exp_spec_one = unreal.MaterialEditingLibrary.create_material_expression_in_function(my_mf, unreal.MaterialExpressionVectorParameter)
            exp_spec_one.set_editor_property("parameter_name", "One")
            exp_spec_one.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))

            exp_add = unreal.MaterialEditingLibrary.create_material_expression_in_function(my_mf,unreal.MaterialExpressionAdd)

            unreal.MaterialEditingLibrary.connect_material_expressions(exp_spec_one, "", exp_add, "A")
            unreal.MaterialEditingLibrary.connect_material_expressions(exp_spec_zero, "", exp_add, "B")

            self.add_test_log("disconnect_expression")
            unreal.PythonMaterialLib.disconnect_expression(exp_add, "B")

            unreal.MaterialEditingLibrary.connect_material_expressions(esp_switch, "", output_node, "")
            unreal.MaterialEditingLibrary.connect_material_expressions(exp_add, "", esp_switch, "True")
            unreal.MaterialEditingLibrary.connect_material_expressions(exp_spec_zero, "", esp_switch, "False")


            unreal.MaterialEditingLibrary.layout_material_function_expressions(my_mf)
            unreal.EditorAssetLibrary.save_asset(my_mf.get_path_name())

            # 2. log mf
            unreal.PythonTestLib.clear_log_buffer()
            unreal.PythonMaterialLib.log_mf(my_mf)
            logs = unreal.PythonTestLib.get_logs(category_regex="PythonTA")
            assert logs, "Logs None"
            assert list(filter(lambda o: "[0] Switch Param (False)/'UseOne'.True <--  Add(,1)" in o, logs)), "Can't find Switch Param in mf logs."
            msgs.append("get mf logs")

            # 3. mf switch
            self.add_test_log("get_mf_static_switch_parameter")
            switches = unreal.PythonMaterialLib.get_mf_static_switch_parameter(my_mf)
            assert switches, "switches None"
            assert len(switches) == 1, "len(switches) != 1"

            self.add_test_log("get_material_function_expressions")
            expressions = unreal.PythonMaterialLib.get_material_function_expressions(my_mf)
            assert expressions, "expressions none"
            assert len(expressions) == 5, f"mf expression count: {len(expressions)} != 5" # output also is a expression
            msgs.append("get_material_function_expressions")

            self.add_test_log("get_material_function_connections")
            connections = unreal.PythonMaterialLib.get_material_function_connections(my_mf)
            assert connections, "connections null"
            assert len(connections) == 4, f"len(connections): {len(connections)} != 4 "
            msgs.append("get_material_connections")

            # 4. expression output
            self.add_test_log("get_material_function_output_expressions")
            output_expresions = unreal.PythonMaterialLib.get_material_function_output_expressions(my_mf)
            assert output_expresions, 'output_expresions None'
            assert len(output_expresions), "get_material_function_output_expressions count 0."

            # 5. get_material_function_content
            self.add_test_log("get_material_function_content")
            mf_content_json = unreal.PythonMaterialLib.get_material_function_content(my_mf)
            json_obj = json.loads(mf_content_json)
            assert len(json_obj) >= 2, "Json object from mf length assert failed"

            succ = True
        except Exception as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)
    

    def _testcase_duplicate_mesh(self):
        succ, msgs = False, []
        try:
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            source_mesh_path = '/Engine/EditorMeshes/ColorCalibrator/SM_ColorCalibrator.SM_ColorCalibrator'
            mesh_path = "/Game/_AssetsForTAPythonTestCase/Meshes/SM_ColorCalibrator_Copied"
            if not unreal.EditorAssetLibrary.does_asset_exist(mesh_path):
                unreal.EditorAssetLibrary.duplicate_asset(source_mesh_path, mesh_path)
                assert unreal.EditorAssetLibrary.does_asset_exist(mesh_path), "None Object after duplicated."
                unreal.EditorAssetLibrary.save_asset(mesh_path)
            msgs.append("Mesh exists.")
            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_mesh_materials(self):
        succ, msgs = False, []
        try:
            mesh_path = "/Game/_AssetsForTAPythonTestCase/Meshes/SM_ColorCalibrator_Copied"
            mesh = unreal.load_asset(mesh_path)
            assert mesh, f"mesh null: {mesh_path}"
            # 1 get materials
            mats = mesh.get_editor_property("static_materials")
            self.add_test_log("get_static_mesh_materials")
            mats_b = unreal.PythonMeshLib.get_static_mesh_materials(mesh)
            assert len(mats) > 0, "material None"
            assert len(mats) == len(mats_b), f"mats count: {len(mats)} != mats_b count: {len(mats_b)}"
            assert mats == mats_b, "mats not equal"
            msgs.append("Get mats")

            # 2. set materials and change the slots names
            slots_names = ["A", "B", "C", "D", "E"]
            assert len(slots_names) == len(mats), f"slots names count != {len(mats)}"

            self.add_test_log("set_static_mesh_materials")
            unreal.PythonMeshLib.set_static_mesh_materials(mesh, materials=mats, slot_names=slots_names)
            msgs.append("set_static_mesh_materials and set slots names")

            # 3.
            another_mesh = unreal.load_asset('/Game/_AssetsForTAPythonTestCase/Meshes/SM_QuarterCylinder')
            self.add_test_log("get_imported_original_mat_names")
            mat_names_in_fbx = unreal.PythonMeshLib.get_imported_original_mat_names(another_mesh)

            assert mat_names_in_fbx and len(mat_names_in_fbx) > 0, "mat_names_in_fbx: Empty"
            assert mat_names_in_fbx[0] == "Fbx Default Material",  f'mat_names_in_fbx[0]: {mat_names_in_fbx[0]} != "Fbx Default Material"'
            msgs.append("Get material name from fbx")

            # 4.get_original_lod_data_count
            self.add_test_log("get_original_lod_data_count")
            lod_data_count = unreal.PythonMeshLib.get_original_lod_data_count(another_mesh)
            assert lod_data_count == 1, f"lod_data_count: {lod_data_count} != 1"

            # 5. get_original_lod_mat_names
            self.add_test_log("get_original_lod_mat_names")
            lod_mat_names= unreal.PythonMeshLib.get_original_lod_mat_names(another_mesh, lod_level= 0)
            assert len(lod_mat_names) == lod_data_count, f"len(lod_mat_names): {len(lod_mat_names)} != lod_data_count: {lod_data_count}"
            assert lod_mat_names[0] == "Fbx Default Material", f'lod_mat_names[0]: {lod_mat_names[0]} != "Fbx Default Material"'
            # 6. lod is_this_lod_generated_by_mesh_reduction

            mesh_subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

            # old ways
            # settings = [unreal.EditorScriptingMeshReductionSettings(percent_triangles, screen_size) for percent_triangles, screen_size in zip([1, 0.5], [1, 0.5])]
            # options = unreal.EditorScriptingMeshReductionOptions(auto_compute_lod_screen_size=False, reduction_settings=settings)
            # unreal.EditorStaticMeshLibrary.set_lods(mesh, options)

            settings = [unreal.StaticMeshReductionSettings(percent_triangles, screen_size) for
                        percent_triangles, screen_size in zip([1, 0.5], [1, 0.5])]
            options = unreal.StaticMeshReductionOptions(auto_compute_lod_screen_size=False, reduction_settings=settings)
            mesh_subsystem.set_lods(mesh, options)
            msgs.append("apply lods")

            # 7.
            self.add_test_log("is_this_lod_generated_by_mesh_reduction")
            bReductions = [unreal.PythonMeshLib.is_this_lod_generated_by_mesh_reduction(mesh, i) for i in range(2)]
            assert bReductions == [True, True], "bReductions != [True, True]: {}".format(", ".join(map(str, bReductions)))
            msgs.append("is this lod generated")

            # 8. swap section0 and section4's material in lod1
            self.add_test_log("set_lod_section_material_slot_index")
            unreal.PythonMeshLib.set_lod_section_material_slot_index(mesh, lod_index=1, section_index=4
                                                                , new_material_slot_index=0, new_material_slot_name="A")
            # new_material_slot_index is the index in material slots,
            unreal.PythonMeshLib.set_lod_section_material_slot_index(mesh, lod_index=1, section_index=0
                                                                     , new_material_slot_index=4, new_material_slot_name="E")
            msgs.append("set_lod_section_material_slot_index")

            # 9. get_sectionl_cast_shadow
            mesh_subsystem.enable_section_cast_shadow(mesh, False, 0, 3)
            self.add_test_log("get_section_cast_shadow")
            before_cast_shadow = unreal.PythonMeshLib.get_section_cast_shadow(mesh, lod_level=0, section_id=3)
            mesh_subsystem.enable_section_cast_shadow(mesh, True, 0, 3)
            after_cast_shadow = unreal.PythonMeshLib.get_section_cast_shadow(mesh, lod_level=0, section_id=3)
            assert before_cast_shadow != after_cast_shadow and after_cast_shadow == True, "before_cast_shadow == after_cast_shadow"

            # 10. socket
            self.add_test_log("get_static_mesh_sockets")
            sockets = unreal.PythonMeshLib.get_static_mesh_sockets(mesh)
            if sockets:
                self.add_test_log("set_static_mesh_sockets")
                unreal.PythonMeshLib.set_static_mesh_sockets(mesh, [])
                sockets = unreal.PythonMeshLib.get_static_mesh_sockets(mesh)
            assert len(sockets) == 0, "get_sectionl_cast_shadow != 0"
            sockets = []
            for i in range(3):
                socket = unreal.StaticMeshSocket()
                socket.set_editor_property("socket_name", f"SocketForTest_{i}")
                socket.relative_location = unreal.Vector.UP * i * 100
                if i == 2:
                    # use set_editor_property_insteady
                    self.add_test_log("set_static_mesh_socket_name")
                    unreal.PythonMeshLib.set_static_mesh_socket_name(socket, "SocketForTest_Renamed")
                sockets.append(socket)
            unreal.PythonMeshLib.set_static_mesh_sockets(mesh, sockets)
            # after set
            after_set = unreal.PythonMeshLib.get_static_mesh_sockets(mesh)
            assert len(after_set) == 3, "len(after_set) != 3"
            socket2_name = after_set[2].get_editor_property("socket_name")
            assert socket2_name == "SocketForTest_Renamed", f"socket2 's name: {socket2_name} != SocketForTest_Renamed"
            msgs.append("get/set mesh socket")

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)

    def _testcase_mesh_misc(self):
        succ, msgs = False, []
        try:
            actor = unreal.PythonBPLib.spawn_actor_from_class(unreal.Actor, unreal.Vector.LEFT * 500)
            actor.set_actor_label("ProceduralMeshForTest")
            mesh_comp = unreal.PythonBPLib.add_component(unreal.ProceduralMeshComponent, actor, actor.root_component)

            mesh_datas = unreal.ProceduralMeshLibrary.generate_box_mesh(unreal.Vector(100, 100, 1000))
            vertices, triangles, normals, u_vs, tangents = mesh_datas

            mesh_comp.create_mesh_section(0, vertices=vertices, triangles=triangles, normals=normals, uv0=u_vs, vertex_colors=[],
                                      tangents=[], create_collision=True)
            # 0
            mat_path = "/Game/_AssetsForTAPythonTestCase/GrassType/Materials/M_Tree"
            assert unreal.EditorAssetLibrary.does_asset_exist(mat_path), f"mat not exists: {mat_path}"
            mi = unreal.load_asset(mat_path)

            mesh_comp.set_material(0, mi)
            # delete existed mesh
            dest_package_path = "/Game/_AssetsForTAPythonTestCase/Meshes/SM_FromProcedural"
            if unreal.EditorAssetLibrary.does_asset_exist(dest_package_path):
                unreal.EditorAssetLibrary.save_asset(dest_package_path)
                unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(unreal.load_asset(dest_package_path))
                unreal.PythonBPLib.delete_asset(dest_package_path, show_confirmation=False)

            assert mesh_comp, "mesh_comp None"
            msgs.append("create procedural mesh")
            # 1.create a procedural mesh
            self.add_test_log("convert_procedural_mesh_to_static_mesh")
            converted_mesh = unreal.PythonMeshLib.convert_procedural_mesh_to_static_mesh(mesh_comp, dest_package_path,
                                                                        recompute_normals=True,
                                                                        recompute_tangents=False,
                                                                        remove_degenerates=False
                                                                        , use_full_precision_u_vs=False,
                                                                        generate_lightmap_u_vs=False)
            assert converted_mesh, "converted_mesh Null"
            assert unreal.EditorAssetLibrary.does_asset_exist(dest_package_path), "dest package null"
            msgs.append("create procedural mesh")

            # 2. convert to static mesh
            asset_data = unreal.EditorAssetLibrary.find_asset_data(dest_package_path)
            assert asset_data, "assert_data from dest_package_path: None"
            unreal.PythonBPLib.sync_to_assets([asset_data], allow_locked_browsers=True, focus_content_browser=True)
            # 3. apply
            self.add_test_log("apply_nanite")
            unreal.PythonMeshLib.apply_nanite(converted_mesh, True)
            # 4 nanite setting
            if unreal.PythonBPLib.get_unreal_version()["major"] == 5:
                settings = converted_mesh.get_editor_property("nanite_settings")
                assert settings, "setting None"
                assert settings.enabled, "settings.enabled == False"
            # 5 generat hism
            hism_actor = unreal.PythonBPLib.spawn_actor_from_class(unreal.Actor, unreal.Vector.ZERO)
            hism_actor.set_actor_label("HismActorForTest")
            hism_comp = unreal.PythonBPLib.add_component(unreal.HierarchicalInstancedStaticMeshComponent, hism_actor, hism_actor.root_component)

            instance_mesh = unreal.load_asset("/Game/StarterContent/Props/SM_Lamp_Ceiling")
            assert instance_mesh, "instance_mesh null"
            hism_comp.set_editor_property("static_mesh", instance_mesh)
            transforms = []

            for y in range(10):
                for x in range(10):
                    transforms.append(unreal.Transform(location=[x * 200, y * 200, 300], rotation=[0, 0, 0], scale=[1, 1, 1]))

            hism_comp.add_instances(transforms, should_return_indices=False)
            # unreal.PythonBPLib.select_none()
            # unreal.PythonBPLib.select_actor(hism_actor, selected=True, notify=True)
            # unreal.PythonBPLib.request_viewport_focus_on_selection(self.get_editor_world())
            unreal.PythonBPLib.set_level_viewport_camera_info(unreal.Vector(-1000, 1500, 1000), unreal.Rotator(0, -30, -30))

            # 6.hism overlaping
            self.add_test_log("get_overlapping_box_count")
            count = unreal.PythonMeshLib.get_overlapping_box_count(hism_comp, box=unreal.Box())
            assert count == 0, "overlapping_box_count = 0"
            box = unreal.Box(min=[0, 200*(-0.5), 100], max=[200*10, 200*(2-0.5), 500])
            unreal.SystemLibrary.draw_debug_box(unreal.EditorLevelLibrary.get_editor_world()
                                                , center=(box.min + box.max)/2
                                                , extent=(box.min + box.max)/2
                                                , line_color=unreal.LinearColor.GREEN
                                                , rotation=unreal.Rotator(0, 0, 0)
                                                , duration=10, thickness=5
                                                )
            count = unreal.PythonMeshLib.get_overlapping_box_count(hism_comp, box=box)
            assert count == 20, f"count: {count} != 20"
            # 7. hism sphere overlaping
            sphere_center = unreal.Vector(1000, 1000, 300) # center of 10 x 10 hism center
            sphere_radius = 200
            self.add_test_log("get_overlapping_sphere_count")
            overlapping_count = unreal.PythonMeshLib.get_overlapping_sphere_count(hism_comp, sphere_center, sphere_radius)
            unreal.SystemLibrary.draw_debug_sphere(unreal.EditorLevelLibrary.get_editor_world(), sphere_center, sphere_radius, segments=36
                                                   , line_color=unreal.LinearColor(1, 0, 0, 0.1), duration=10, thickness=2)
            assert overlapping_count == 5, f"count: {overlapping_count} != 5"
            msgs.append("hism overlapping.")

            # 8.
            mesh_path = "/Game/_AssetsForTAPythonTestCase/Meshes/SM_ColorCalibrator_Copied"

            if not unreal.EditorAssetLibrary.does_asset_exist(mesh_path):
                source_mesh_path = '/Engine/EditorMeshes/ColorCalibrator/SM_ColorCalibrator.SM_ColorCalibrator'
                unreal.EditorAssetLibrary.duplicate_asset(source_mesh_path, mesh_path)

            mesh = unreal.load_asset(mesh_path)

            self.add_test_log("get_static_mesh_section_info")
            material_indexes = unreal.PythonBPLib.get_static_mesh_section_info(mesh, 0)
            assert material_indexes, "material_indexes None"
            msgs.append("material_indexes.")

            # 9 set_static_mesh_lod_material_id
            for i in range(len(material_indexes)):
                if i == 0:
                    self.add_test_log("set_static_mesh_lod_material_id")
                unreal.PythonBPLib.set_static_mesh_lod_material_id(mesh, 0, i, len(material_indexes) - i -1, modify_immediately=True)

            self.add_test_log("get_static_mesh_section_info")
            material_indexes_after = unreal.PythonBPLib.get_static_mesh_section_info(mesh, 0)

            print(type(material_indexes))
            print(type(list(material_indexes)))
            print(type(list(reversed(material_indexes_after))))
            assert len(material_indexes) == len(material_indexes_after), f"len(material_indexes): {len(material_indexes)} != len(material_indexes_after) : {len(material_indexes_after)}"
            for a, b in zip(material_indexes, reversed(material_indexes_after)):
                assert a == b, f"material_indexes_after: {b} != {a}"

            for i in range(len(material_indexes)):
                unreal.PythonBPLib.set_static_mesh_lod_material_id(mesh, 0, i, material_indexes[i], modify_immediately=True)

            msgs.append("set_static_mesh_lod_material_id.")

            # 10. anim bp set_anim_blueprint
            # c.set_editor_property("animation_blueprint", _r.generated_class())

            # skeletal_asset_path = "/Game/FirstPersonArms/Character/Mesh/SK_Mannequin_Arms.SK_Mannequin_Arms"
            # animbp_path = '/Game/FirstPersonArms/Animations/FirstPerson_AnimBP'
            skeletal_asset_path = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP_Skeleton.TutorialTPP_Skeleton"
            animbp_path = '/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP_AnimBlueprint'

            assert unreal.EditorAssetLibrary.does_asset_exist(skeletal_asset_path), f"skeletal_asset_path: {skeletal_asset_path}, not exists."
            assert unreal.EditorAssetLibrary.does_asset_exist(animbp_path), f"animbm_path: {animbp_path}, not exists."
            skeletal = unreal.load_asset(skeletal_asset_path)
            animbp = unreal.load_asset(animbp_path)
            assert skeletal, "skeletal none"
            assert animbp, "animbp none"

            skeletal_actor = unreal.PythonBPLib.spawn_actor_from_object(skeletal, unreal.Vector.BACKWARD * 2_00)
            assert skeletal_actor.skeletal_mesh_component , "skeletal_mesh.skeletal_mesh_component none"
            ske_comp = skeletal_actor.skeletal_mesh_component
            # use comp.set_editor_property("anim_class", animbp.generated_class()) instead
            self.add_test_log("set_anim_blueprint")
            unreal.PythonBPLib.set_anim_blueprint(ske_comp, animbp)
            #
            self.add_test_log("get_anim_blueprint_generated_class")
            assert unreal.PythonBPLib.get_anim_blueprint_generated_class(animbp) == ske_comp.get_editor_property("anim_class"), "anim_blueprint_generated_class failed"
            assert unreal.PythonBPLib.get_anim_blueprint_generated_class(animbp) == animbp.generated_class(), "get_anim_blueprint_generated_class failed"
            msgs.append("set_anim_blueprint/get_anim_blueprint_generated_class.")

            succ = True
        except AssertionError as e:
            msgs.append(str(e))

        self.push_result(succ, msgs)



    def test_category_Mesh(self, id):
        self.test_being(id=id)
        level_path = '/Game/StarterContent/Maps/StarterMap'  # avoid saving level by mistake
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_texture), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_close_temp_assets_editor), delay_seconds=1)
        self.push_call(py_task(self._testcase_create_rt), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_set_rt), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_create_swtich_materials), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_material_attributes), delay_seconds=0.1)

        self.push_call(py_task(self._testcase_duplicate_mesh), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_mesh_materials), delay_seconds=0.1)

        level_path = '/Game/_AssetsForTAPythonTestCase/Maps/NewMap'
        self.push_call(py_task(unreal.EditorLevelLibrary.load_level, level_path), delay_seconds=0.1)
        self.push_call(py_task(self._testcase_mesh_misc), delay_seconds=0.1)



        self.test_finish(id)




