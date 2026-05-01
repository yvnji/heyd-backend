import boto3
import zipfile
import requests
import os
import shutil
from dotenv import load_dotenv, set_key, dotenv_values


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


def list_lambda_names():
    """src 폴더 안에 있는 Lambda 이름 리스트"""
    lambda_list = []
    for ln in os.listdir(src_path):
        if ln == ".DS_Store":
            continue
        lambda_list.append(ln)
    return sorted(lambda_list)


def download_lambda_code_all(qualifier=None):
    """src 폴더 안에 있는 모든 Lambda 코드 다운로드"""
    for lambda_name in list_lambda_names():
        try:
            download_lambda_code(lambda_name, qualifier)
        except Exception as e:
            print(f"\n[ERROR {lambda_name}] : {e}\n")


def download_lambda_code(function_name=None, qualifier=None):
    """Lambda 코드 다운로드 (현재 Local에 있는 코드는 삭제하고 새로 다운로드)"""
    if not function_name:
        function_name = input("Function name : ")
    download_path = f"./{function_name}.zip"

    # Lambda 함수 코드 URL 가져오기
    if qualifier:
        response = lambda_client.get_function(
            FunctionName=function_name, Qualifier=qualifier
        )
    else:
        response = lambda_client.get_function(FunctionName=function_name)
    code_location = response["Code"]["Location"]
    # lambda_version = response["Configuration"]["Version"]

    # 코드 다운로드
    with requests.get(code_location, stream=True) as r:
        r.raise_for_status()
        with open(download_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # Local에 있는 해당 Lambda Code 삭제
    delete_directory(f"./src/{function_name}")

    # 새로운 코드 저장
    with zipfile.ZipFile(download_path, "r") as zip_ref:
        zip_ref.extractall(f"./src/{function_name}")
    os.remove(download_path)

    qual_str = qualifier if qualifier else "$LATEST"
    print(f"[Download Code] {function_name}:{qual_str}")

    # 환경변수 저장
    # save_lambda_env_variables_to_env_file(function_name, qualifier)
    # print()

    # .lambda_versions에 lambda version 저장
    # if function_name not in lambda_without_alias:
    #     set_key_sort(
    #         lambda_versions_path, "/".join([region_at, function_name]), lambda_version
    #     )


def save_lambda_env_variables_to_env_file_all(qualifier=None):
    """모든 Lambda 환경변수 저장"""
    for lambda_name in list_lambda_names():
        save_lambda_env_variables_to_env_file(lambda_name, qualifier)


def save_lambda_env_variables_to_env_file(function_name=None, qualifier=None):
    """Lambda에 적용 되어 있는 환경변수를 .env 파일로 저장"""
    if not function_name:
        function_name = input("Function name : ")

    # Lambda 함수의 환경 변수 가져오기 (특정 버전이나 별칭으로 지정)
    if qualifier:
        response = lambda_client.get_function_configuration(
            FunctionName=function_name, Qualifier=qualifier
        )
    else:
        response = lambda_client.get_function_configuration(FunctionName=function_name)

    env_vars = response.get("Environment", {}).get("Variables", {})

    # .env 파일로 저장
    with open(f"./src/{function_name}/.env", "w") as f:
        for key in sorted(env_vars):
            f.write(f"{key}={env_vars[key]}\n")

    qual_str = qualifier if qualifier else "$LATEST"
    print(f"[Download env] {function_name}:{qual_str}")


def get_lambda_layers_all(qualifier=None):
    """src 폴더 안 모든 Lambda에 적용 되어 있는 Layer 조회"""
    for lambda_name in list_lambda_names():
        try:
            get_lambda_layers(lambda_name, qualifier)
        except Exception as e:
            print(f"\n[ERROR {lambda_name}] : {e}\n")


def get_lambda_layers(function_name=None, qualifier=None):
    """Lambda에 적용 되어 있는 Layer 조회"""
    if not function_name:
        function_name = input("Function name : ")

    # Lambda 함수 설정 정보 가져오기 (특정 버전이나 별칭으로 지정)
    if qualifier:
        response = lambda_client.get_function_configuration(
            FunctionName=function_name, Qualifier=qualifier
        )
    else:
        response = lambda_client.get_function_configuration(FunctionName=function_name)

    # Layers 정보 추출
    layers = response.get("Layers", [])
    qual_str = qualifier if qualifier else "$LATEST"
    print(f"{function_name}:{qual_str} 함수에서 사용 중인 Layers")
    for layer in layers:
        print(f"- {layer['Arn']}")
    print()


def delete_directory(dir_path):
    """특정 폴더 삭제"""
    try:
        shutil.rmtree(dir_path)
        print(f"'{dir_path}'가 성공적으로 삭제되었습니다.")
    except FileNotFoundError:
        pass


def download_lambda_layer(layer_name=None, version_number=None):
    """Layer 코드 다운로드 (Local에 있는 기존 코드 삭제)"""
    download_path = f"./layer/{layer_name}.zip"
    layer_path = f"./layer/{layer_name}"

    # 지정한 Layer 버전 정보 가져오기
    response = lambda_client.get_layer_version(
        LayerName=layer_name, VersionNumber=version_number
    )
    layer_version_arn = response["LayerArn"]

    # Layer의 코드 위치(URL) 가져오기
    code_location = response["Content"]["Location"]

    # ZIP 파일 다운로드
    with requests.get(code_location, stream=True) as r:
        r.raise_for_status()
        with open(download_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # Local에 있는 Layer Code 삭제
    delete_directory(layer_path)

    # 새로운 코드 저장
    with zipfile.ZipFile(download_path, "r") as zip_ref:
        zip_ref.extractall(layer_path)
    os.remove(download_path)

    # 환경변수에 현재 저장된 Layer Version 저장
    set_key_sort(
        layer_versions_path,
        "/".join([region_at, layer_name]),
        f"{layer_version_arn}:{version_number}",
    )


def get_alias_version_all(qualifier):
    """모든 lambda alias 조회"""
    for lambda_name in list_lambda_names():
        try:
            get_alias_version(lambda_name, qualifier)
        except Exception as e:
            print(f"\n[ERROR {lambda_name}] : {e}\n")


def get_alias_version(function_name=None, alias=None):
    """Lambda alias의 version 조회"""
    if not function_name:
        function_name = input("Function name : ")

    response = lambda_client.get_alias(FunctionName=function_name, Name=alias)

    print(f'{function_name}:{alias} version : {response["FunctionVersion"]}')


if __name__ == "__main__":
    print("Region")
    print("1. Seoul (ap-northeast-2)")
    print("2. Virginia (us-east-1)\n")
    key = input("Select : ")
    region = {"1": "ap-northeast-2", "2": "us-east-1"}
    region_at = region[key]
    lambda_client = boto3.client("lambda", region_name=region_at)

    print("\n1. Lambda 코드 다운로드 (전체)")
    print("2. Lambda 코드 다운로드")
    print("3. Lambda 적용중인 Layer 조회 (전체)")
    print("4. Lambda 적용중인 Layer 조회")
    print("5. Layer 다운로드")
    print("6. 환경변수만 다운로드 (전체)")
    print("7. 환경변수만 다운로드")
    print("8. Lambda Version 조회")
    key = input("Select : ")
    print()

    qualifier = input("Alias or Version? : ")
    if not qualifier:
        qualifier = None

    methods = {
        "1": download_lambda_code_all,
        "2": download_lambda_code,
        "3": get_lambda_layers_all,
        "4": get_lambda_layers,
        "5": download_lambda_layer,
        "6": save_lambda_env_variables_to_env_file_all,
        "7": save_lambda_env_variables_to_env_file,
        "8": get_alias_version_all,
    }

    params = {"qualifier": qualifier}
    if key == "5":
        layer_name = input("Layer name : ")
        params = {"layer_name": layer_name, "version_number": int(qualifier)}
    methods[key](**params)
