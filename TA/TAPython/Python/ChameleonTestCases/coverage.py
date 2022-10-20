import os
import re
from typing import List
from dataclasses import dataclass




def get_all_py_functions_ori(folder):
    blacklist = {"PythonCommandExecutionMode", "PythonFileExecutionScope", "PythonGeneratedClass"
                , "PythonLogOutputEntry", "PythonMaterialInfosDelegate", "PythonScriptLibrary"
                 }
    py_stubs = []
    chameleon_file = None
    for root, folders, files in os.walk(folder):
        py_stubs.extend([os.path.join(root, f) for f in files if f.startswith("Python") and f.endswith("Lib.py")])
        if not chameleon_file:
            for f in files:
                py = "ChameleonData.py"
                if f == py:
                    chameleon_file = os.path.join(root, f)

    print(f"py_stub: {len(py_stubs)}")

    result = []
    for file_name in py_stubs:
        with open(file_name, 'r', encoding="UTF-8") as f:
            for line in f.readlines():
                if line.startswith("    def "):
                    function_name = line[8:line.find("(")]
                    lib_name = os.path.basename(file_name).split(".")[0]
                    result.append(f"{lib_name}.{function_name}")
    print("all function count:", len(result))
    return result

def get_all_py_functions(folder):
    py_md = []
    chamaleon_file = None
    for file_name in os.listdir(folder):
        if not chamaleon_file and file_name == "ChameleonData.md":
            chamaleon_file = os.path.join(folder, file_name)
        else:
            if file_name.startswith("Python"):
                py_md.append(os.path.join(folder, file_name))
    py_md.append(chamaleon_file)

    result = []

    for file_name in py_md:
        with open(file_name, 'r', encoding="UTF-8") as f:
            for line in f.readlines():
                if line.startswith('### <a id="'):
                    function_name = line[11 : line[11:].find('"')+11]
                    lib_name = os.path.basename(file_name).split(".")[0]
                    result.append(f"{lib_name}.{function_name}")
    print("all function count:", len(result))
    return result




class FileFunctionCutter:
    def __init__(self, file_path):
        self.file_path = file_path
        self.lookups = dict()

    def apply_counter(self, filter_func=None):
        with open(self.file_path, 'r', encoding="UTF-8") as f:
            for line in f.readlines():
                if not line or len(line) < 2:
                    continue
                splits = re.split(' |,|\n|\(|\)|\*|\[|\]|\-|/|\\|;|{|}|#|"|=', line)
                for s in splits:
                    if filter_func and not filter_func(s):
                        continue

                    if s not in self.lookups:
                        self.lookups[s] = 0
                    self.lookups[s] += 1


    def print_log(self):
        # keys, values = self.lookups.keys(), self.lookups.values()
        for k, v in self.lookups.items():
            print(f"{k}: {v}")


@dataclass
class FileCounter:
    py_files: [str]
    json_files: [str]




def get_used_functions(folder, file_white_list:List[str]):

    file_counter = FileCounter([], [])

    for root, folders, files in os.walk(folder):
        if root.endswith("/unreal") or root.endswith("\\unreal"):
            continue
        for file_name in files:
            if file_white_list and file_name not in file_white_list:
                continue
            lower_name = file_name.lower()
            if not ( lower_name.endswith(".py") or lower_name.endswith(".json")):
                continue
            bPy = lower_name.endswith(".py")
            if bPy:
                file_counter.py_files.append(os.path.join(root, file_name))
            else:
                file_counter.json_files.append(os.path.join(root, file_name))

    all = dict()
    def combine_dict(ori_dict, new_dict):
        for k, v in new_dict.items():
            if "im.data." in k:
                continue
            if ".data." in k and "self.data." not in k:
                k = "self" + k[k.find(".data"):]

            if k not in ori_dict:
                ori_dict[k] = 0
            ori_dict[k] += v
        return ori_dict

    print("----" * 10)
    print(f"pyfiles: {len(file_counter.py_files)}")
    for file_path in file_counter.py_files:
        k = FileFunctionCutter(file_path)
        k.apply_counter(lambda o: ("unreal.Python" in o and "Lib." in o) or ".data." in o or "unreal.ChameleonData." in o)
        # k.print_log()
        combine_dict(all, k.lookups)

    print("~~~~" * 10)

    for json_file in file_counter.json_files:
        # print(json_file)
        k = FileFunctionCutter(json_file)
        # k.apply_counter(lambda o: "self.data." in o and "ChameleonData.data." in o)
        k.apply_counter(lambda o: ("unreal.Python" in o and "Lib." in o) or ".data." in o or "unreal.ChameleonData." in o)
        k.print_log()

        combine_dict(all, k.lookups)

    print("====" * 10)
    for k, v in all.items():
        print(f"{k}\t{v}")
    return all



@dataclass
class lib_Statistics:
    lib_name : str
    function_number : int
    tested_number : int
    tested_range : float
    function_details : []


    def __hash__(self):
        return hash(self.lib_name)

    def get_not_tested_function_names(self):
        # print(f"\tfunction_details: {len(self.function_details)}")
        return [func_name for func_name, bTested in self.function_details if not bTested]




def export_report(file_path:str, all_function_names:[str], counts:[int]):
    libs = {}

    with open(file_path, 'w', encoding="UTF-8") as f:
        f.write("|Lib|Function Name | Count | ||\n")
        f.write("|:--- |:---- | :----| :----| :----|\n")
        for i, (function_name, count) in enumerate(zip(all_function_names, counts)):
            lib_name, name = function_name.rsplit(".", 2)
            f.write(f"|{lib_name}|{name}|{count}|||\n")
            # summary
            if lib_name not in libs:
                libs[lib_name] = lib_Statistics(lib_name, 0, 0, 0, [])
            libs[lib_name].function_number += 1
            libs[lib_name].tested_number += 1 if count > 0 else 0

            libs[lib_name].function_details.append([name, count > 0])

        f.write('\n')
        f.write("|Lib|Function Count | Tested Count | Tested Rate||\n")
        f.write("|:--- |:---- | :----| :----| :----|\n")
        print("\n")
        for k, statistics in libs.items():
            tested_rate = statistics.tested_number / statistics.function_number
            f.write(f"|{statistics.lib_name}|{statistics.function_number}|{statistics.tested_number}|{tested_rate:%}||\n")
            print(f"{statistics.lib_name:20} {statistics.tested_number} / {statistics.function_number}:   {tested_rate:.1%}")

            if statistics.function_number - statistics.tested_number < 30:
                for func_name in statistics.get_not_tested_function_names():
                    print(f"\t{func_name}")
                # print("\t{}".format(", ".join(statistics.get_not_tested_function_names())))






        f.write('\n')




if __name__ == "__main__":
    all_function_names = get_all_py_functions("../ChameleonDocGenerator/Generated")
    counts = [-1] * len(all_function_names)
    print(all_function_names)

    all_used = get_used_functions("../ChameleonTestCases", file_white_list=["TestPythonAPIs.py"])
    for i, function_name in enumerate(all_function_names):
        count = 0
        if "unreal." + function_name in all_used:
            count = all_used["unreal." + function_name]
        elif function_name.startswith("ChameleonData."):
            k = "self.data." + function_name[len("ChameleonData.") :]
            if k in all_used:
                count = all_used[k]
        counts[i] = count



    export_report(__file__[:-2] + "md", all_function_names, counts)


