#!/usr/bin/env python3
# encoding: utf-8

"获取 115 文件信息和下载链接"
import os

working_directory = os.path.dirname(os.path.abspath(__file__))
os.chdir(working_directory)


__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from argparse import ArgumentParser, RawTextHelpFormatter
from os.path import expanduser, dirname, join as joinpath
from posixpath import dirname, realpath
from urllib.parse import quote, unquote
from collections.abc import Callable


try:
    from p115 import P115FileSystem
    from posixpatht import escape
except ImportError:
    from sys import executable
    from subprocess import run

    run(
        [
            executable,
            "-m",
            "pip",
            "install",
            "-U",
            "fastapi",
            "uvicorn",
            "jinja2",
            "posixpatht",
            "python-115",
        ],
        check=True,
    )
    from p115 import P115FileSystem
    from posixpatht import escape

try:
    from orjson import dumps
except ImportError:
    try:
        from ujson import dumps as odumps
    except ImportError:
        from json import dumps as odumps
    dumps = lambda obj: bytes(odumps(obj, ensure_ascii=False), "utf-8")

parser = ArgumentParser(
    formatter_class=RawTextHelpFormatter,
    description="获取 115 文件信息和下载链接",
    epilog="""
---------- 使用说明 ----------

你可以打开浏览器进行直接访问。

1. 如果想要访问某个路径，可以通过查询接口

    GET /{path}

或者

    GET /?path={path}

也可以通过 pickcode 查询

    GET /?pickcode={pickcode}

也可以通过 id 查询

    GET /?id={id}

2. 查询文件或文件夹的信息，返回 json

    GET /?method=attr

3. 查询文件夹内所有文件和文件夹的信息，返回 json

    GET /?method=list

4. 查询文件或文件夹的备注

    GET /?method=desc

5. 支持的查询参数

 参数    | 类型    | 必填 | 说明
-------  | ------- | ---- | ----------
pickcode | string  | 否   | 文件或文件夹的 pickcode，优先级高于 id
id       | integer | 否   | 文件或文件夹的 id，优先级高于 path
path     | string  | 否   | 文件或文件夹的路径，优先级高于 url 中的路径部分
method   | string  | 否   | 1. 'url': 【默认值】，这个文件的下载链接
         |         |      | 2. 'attr': 这个文件或文件夹的信息
         |         |      | 3. 'list': 这个文件夹内所有文件和文件夹的信息
         |         |      | 4. 'desc': 这个文件或文件夹的备注
""",
)
parser.add_argument(
    "-H", "--host", default="0.0.0.0", help="ip 或 hostname，默认值 '0.0.0.0'"
)
parser.add_argument("-p", "--port", default=80, type=int, help="端口号，默认值 80")
parser.add_argument(
    "-c",
    "--cookies",
    help="115 登录 cookie，如果缺失，则从 115-cookies.txt 文件中获取，此文件可以在 当前工作目录、此脚本所在目录 或 用户根目录 下",
)
parser.add_argument(
    "-pc", "--use-path-cache", action="store_true", help="启用 path 到 id 的缓存"
)
parser.add_argument("-v", "--version", action="store_true", help="输出版本号")
args = parser.parse_args()
if args.version:
    print(".".join(map(str, __version__)))
    raise SystemExit(0)

cookies = None
path_cache = None  # type: None | dict
if args.cookies:
    cookies = args.cookies
if args.use_path_cache:
    path_cache = {}
if not cookies:
    seen = set()
    for dir_ in (".", expanduser("~"), dirname(__file__)):
        dir_ = realpath(dir_)
        if dir_ in seen:
            continue
        seen.add(dir_)
        try:
            cookies = open(joinpath(dir_, "115-cookies.txt")).read()
            if cookies:
                break
        except FileNotFoundError:
            pass

fs = P115FileSystem.login(cookies, path_to_id=path_cache)
if not cookies and fs.client.cookies != cookies:
    open("115-cookies.txt", "w").write(fs.client.cookies)

KEYS = (
    "id",
    "parent_id",
    "name",
    "path",
    "sha1",
    "pickcode",
    "is_directory",
    "size",
    "ctime",
    "mtime",
    "atime",
    "thumb",
    "star",
    "labels",
    "score",
    "hidden",
    "described",
    "violated",
    "url",
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="./templates")


def get_url_with_pickcode(pickcode: str, request: Request):
    headers = {}
    for key, val in request.headers.items():
        if key.lower() == "user-agent":
            headers["User-Agent"] = val
            break
    try:
        url = fs.get_url_from_pickcode(pickcode, detail=True, headers=headers)
        return RedirectResponse(url)
    except OSError:
        raise HTTPException(status_code=404, detail="Not Found")


@app.get("/")
async def index(request: Request):
    return await query("/", request)


@app.get("/{path:path}")
async def query(path: str, request: Request):
    method = request.query_params.get("method", "url")
    pickcode = request.query_params.get("pickcode")
    fid = request.query_params.get("id")
    url = unquote(str(request.url))
    try:
        origin = url[: url.index("/", 8)]
    except ValueError:
        origin = url

    def append_url(attr):
        path_url = attr.get("path_url") or "%s%s" % (
            origin,
            quote(attr["path"], safe=":/"),
        )
        if attr["is_directory"]:
            attr["url"] = f"{path_url}?id={attr['id']}"
        else:
            attr["url"] = f"{path_url}?pickcode={attr['pickcode']}"
        return attr

    if method == "attr":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                attr = fs.attr(int(fid))
            else:
                path = request.query_params.get("path") or path
                attr = fs.attr(path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Not Found")
        append_url(attr)
        json_str = dumps({k: attr.get(k) for k in KEYS})
        return Response(content=json_str, media_type="application/json; charset=utf-8")
    elif method == "list":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                children = fs.listdir_attr(int(fid))
            else:
                path = request.query_params.get("path") or path
                children = fs.listdir_attr(path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Not Found")
        except NotADirectoryError as exc:
            raise HTTPException(status_code=400, detail=f"Bad Request: {exc}")
        json_str = dumps(
            [{k: attr.get(k) for k in KEYS} for attr in map(append_url, children)]
        )
        return Response(content=json_str, media_type="application/json; charset=utf-8")
    elif method == "desc":
        try:
            if pickcode:
                fid = fs.get_id_from_pickcode(pickcode)
            if fid is not None:
                return fs.desc(int(fid))
            else:
                path = request.query_params.get("path") or path
                return fs.desc(path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Not Found")
    if pickcode:
        return get_url_with_pickcode(pickcode, request)
    try:
        if fid is not None:
            attr = fs.attr(int(fid))
        else:
            path = request.query_params.get("path") or path
            attr = fs.attr(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not Found")
    if not attr["is_directory"]:
        return get_url_with_pickcode(attr["pickcode"], request)
    try:
        children = fs.listdir_attr(attr["id"])
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=f"Bad Request: {exc}")
    for subattr in children:
        subattr["path_url"] = "%s%s" % (origin, quote(subattr["path"], safe=":/"))
        append_url(subattr)
    fid = attr["id"]

    if fid == 0:
        header = f'<strong><a href="{origin}?id=0" style="text-decoration: none">/115</a></strong>'
    else:
        ancestors = fs.get_ancestors(int(attr["id"]))
        info = ancestors[-1]
        header = (
            f'<strong><a href="{origin}?id=0" style="text-decoration: none">/115</a></strong>'
            + "/"
            + "".join(
                f'<strong><a href="{origin}?id={info["id"]}" style="text-decoration: none">{escape(info["name"])}</a></strong>/'
                for info in ancestors[1:-1]
            )
            + f'<strong><a href="{origin}?id={info["id"]}&method=list" style="text-decoration: none">{escape(info["name"])}</a></strong>'
        )
        # 在后端处理 children 列表中的数据,并保存修改
    header = f'<div id="nav-link">{header}</div>'
    processed_children = []
    for attr in children:
        if attr["is_directory"]:
            processed_attr = {**attr, "size": "--"}
        else:
            processed_attr = {**attr, "size": f"{attr['size'] / 1024/1024/1024:.2f} GB"}
        if not attr["is_directory"]:
            name = attr["name"]
            if name.endswith(
                (
                    ".mkv",
                    ".iso",
                    ".ts",
                    ".mp4",
                    ".avi",
                    ".rmvb",
                    ".wmv",
                    ".m2ts",
                    ".mpg",
                    ".flv",
                    ".rm",
                    ".mov",
                )
            ):
                processed_attr = {**processed_attr, "is_media": True}
        processed_children.append(processed_attr)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "attr": attr,
            "children": processed_children,
            "origin": origin,
            "header": header,
        },
    )


if __name__ == "__main__":
    uvicorn.run("web:app", host="0.0.0.0", port=80, reload=True)
