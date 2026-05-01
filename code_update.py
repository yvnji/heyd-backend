import boto3
import os
import zipfile
import time
from dotenv import load_dotenv, dotenv_values, set_key


lambda_client = None
region_at = None
src_path = "./src"
lambda_versions_path = "./.lambda_versions"
layer_versions_path = "./layer/.layer_arn"
lambda_without_alias = ["idolmaster-error-alarm"]


def set_key_sort(path, key, value):
    load_dotenv(path)
    env_vars = dotenv_values(path)
    env_vars[key] = value

    sorted_env_vars = dict(sorted(env_vars.items()))

    with open(path, "w"):
        for key, value in sorted_env_vars.items():
            set_key(path, key, value)


def deploy_alias():
    lambda_versions_local = dotenv_values(lambda_versions_path)
    alias = input("Alias : ")
    for lambda_name in list_lambda_names():
        if lambda_name in lambda_without_alias:
            continue
        key = "/".join([region_at, lambda_name])
        deploy_version(lambda_name, alias, lambda_versions_local[key])


def deploy_version(lambda_name, alias, local_version):
    try:
        latest_alias_version = lambda_client.get_alias(
            FunctionName=lambda_name, Name=alias
        )["FunctionVersion"]
    except Exception:
        print("Invalid Lambda : %s:%s" % (lambda_name, alias))
        return

    if local_version == latest_alias_version:
        print("[Deployed alias]")
        print("Lambda : %s" % lambda_name)
        print("Alias : %s" % alias)
        print("Version : %s" % latest_alias_version)

    else:
        lambda_client.update_alias(
            FunctionName=lambda_name, Name=alias, FunctionVersion=local_version
        )
        print("[Deploy new alias]")
        print("Lambda : %s" % lambda_name)
        print("Alias : %s" % alias)
        print("Version : %s -> %s\n" % (latest_alias_version, local_version))
    return latest_alias_version, local_version


def get_object_zip(zip_path):
    ret = None
    owd = os.getcwd()
    os.chdir(zip_path)
    zip_file_name = "output.zip"
    zip_file = zipfile.ZipFile(zip_file_name, "w")
    for path, dirs, files in os.walk("."):
        if "__MACOSX" in dirs:
            dirs.remove("__MACOSX")
        for file in files:
            if (
                file == zip_file_name
                or file.endswith(".pyc")
                or file.endswith(".env")
                or file.endswith(".DS_Store")
            ):
                continue
            zip_file.write(os.path.join(path, file), compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()
    with open(zip_file_name, "rb") as f:
        ret = f.read()
    os.remove(zip_file_name)
    os.chdir(owd)
    return ret


def list_lambda_names():
    lambda_list = []
    for ln in os.listdir(src_path):
        if ln == ".DS_Store":
            continue
        lambda_list.append(ln)
    return lambda_list


def list_versions_by_lambda(lambda_name, marker=None):
    params = {"FunctionName": lambda_name}
    if marker:
        params["Marker"] = marker
    res = lambda_client.list_versions_by_function(**params)
    list_versions = [v["Version"] for v in res["Versions"]]
    if res.get("NextMarker"):
        list_versions += list_versions_by_lambda(lambda_name, marker=res["NextMarker"])
    try:
        list_versions.remove("$LATEST")
    except Exception:
        pass
    return sorted(list_versions, key=lambda r: int(r))


def update_layer_code():
    layer_name = input("Layer name : ")
    desc = input("Layer description : ")
    path = f"./layer/{layer_name}"
    object_zip = get_object_zip(path)
    res_pub = lambda_client.publish_layer_version(
        LayerName=layer_name,
        Description=desc,
        Content={"ZipFile": object_zip},
        LicenseInfo="MIT",
        CompatibleRuntimes=["python3.9", "python3.10"],
    )
    print("[Update Layer Code]")
    print("Layer : %s" % layer_name)
    print("Description : %s" % desc)
    print("Version : %d\n" % res_pub["Version"])
    set_key_sort(
        layer_versions_path,
        "/".join([region_at, layer_name]),
        f"{res_pub['LayerArn']}:{res_pub['Version']}",
    )

    # print('[Attach Layer]')
    # for lambda_name in list_lambda_names():
    #     res = lambda_client.update_function_configuration(
    #         FunctionName = lambda_name,
    #         Layers = [
    #             res_pub['LayerVersionArn']
    #         ]
    #     )
    #     print(lambda_name)


def update_layer_to_lambda_all(layer_name=None):
    if not layer_name:
        layer_name = input("Layer name : ")
    for lambda_name in list_lambda_names():
        update_layer_to_lambda(layer_name, lambda_name)


def update_layer_to_lambda(layer_name=None, lambda_name=None):
    if not layer_name:
        layer_name = input("Layer name : ")
    if not lambda_name:
        lambda_name = input("Lambda name : ")

    res_layers = lambda_client.get_function_configuration(FunctionName=lambda_name).get(
        "Layers", []
    )
    layer_arn_list = []
    for layer in res_layers:
        arn_split = layer["Arn"].split(":")
        if arn_split[-2] == layer_name:
            continue
        layer_arn_list.append(layer["Arn"])
    key = "/".join([region_at, layer_name])
    layer_arn_list.append(dotenv_values(layer_versions_path)[key])
    lambda_client.update_function_configuration(
        FunctionName=lambda_name, Layers=layer_arn_list
    )


def update_function_code(lambda_name=None, publish=False):

    if not lambda_name:
        lambda_name = input("Function name : ")

    # 환경변수 업로드
    # env_path = f'./src/{lambda_name}/.env'
    # env_variables = dotenv_values(env_path)
    # update_lambda_environment(lambda_name, env_variables)

    path = os.path.join(src_path, lambda_name)
    object_zip = get_object_zip(path)
    while True:
        try:
            res = lambda_client.update_function_code(
                FunctionName=lambda_name, ZipFile=object_zip, Publish=publish
            )

            print("[Update Function Code]")
            print("Lambda : %s" % lambda_name)
            print("Layer : %s" % res.get("Layers", []))
            print("New version : %s" % res["Version"])
            # if lambda_name not in lambda_without_alias:
            #     set_key_sort(
            #         lambda_versions_path,
            #         "/".join([region_at, lambda_name]),
            #         res["Version"],
            #     )
            break
        except lambda_client.exceptions.PreconditionFailedException as e:
            print(e)
            print(
                "Failed to publish version: The function code was updated by another user."
            )


def update_function_code_all(publish=None):
    for lambda_name in list_lambda_names():
        update_function_code(lambda_name, publish)


def update_lambda_environment(function_name, env_variables):
    res = lambda_client.update_function_configuration(
        FunctionName=function_name, Environment={"Variables": env_variables}
    )

    while True:
        time.sleep(1)
        res = lambda_client.get_function(FunctionName=function_name)
        if res["Configuration"]["State"] == "Active":
            break


if __name__ == "__main__":
    print("Region")
    print("1. Seoul (ap-northeast-2)")
    print("2. Virginia (us-east-1)\n")
    key = input("Select : ")
    region = {"1": "ap-northeast-2", "2": "us-east-1"}
    region_at = region[key]
    lambda_client = boto3.client("lambda", region_name=region_at)

    print("\n1. Lambda 코드 업데이트 (전체)")
    print("2. Lambda 코드 업데이트")
    print("3. 업데이트된 코드 배포")
    print("4. Layer 업데이트")
    print("5. Layer를 전체 Lambda에 적용")
    print("6. Layer를 Lambda에 적용\n")
    key = input("Select : ")
    print()

    methods = {
        "1": update_function_code_all,
        "2": update_function_code,
        "3": deploy_alias,
        "4": update_layer_code,
        "5": update_layer_to_lambda_all,
        "6": update_layer_to_lambda,
    }
    if key in ["1", "2"]:
        pub = input("Publish version? (y,n) : ")
        if pub.lower() == "y":
            pub = True
        elif pub.lower() == "n":
            pub = False
        methods[key](publish=pub)
    else:
        methods[key]()
