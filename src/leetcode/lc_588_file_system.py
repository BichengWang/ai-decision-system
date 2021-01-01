from typing import List
from enum import Enum


class FileSystem:

    def __init__(self):
        self.dummy = Node("", NodeType.DIR)
        self.dummy.node_dict[""] = Node("", NodeType.DIR)
        self.current_dir = self.dummy.node_dict[""]

    def ls(self, path: str) -> List[str]:
        ret = list()
        path_list = path.split("/") if len(path) > 1 else ['']
        cur_node = self.dummy
        for p in path_list:
            if p not in cur_node.node_dict:
                return ret
            cur_node = cur_node.node_dict[p]
            if cur_node.node_type != NodeType.DIR:
                return ret
        return sorted(cur_node.node_dict.keys())

    def mkdir(self, path: str) -> None:
        path_list = path.split("/")
        cur_node = self.dummy
        for p in path_list:
            if p not in cur_node.node_dict:
                cur_node.node_dict[p] = Node(p, NodeType.DIR)
            cur_node = cur_node.node_dict[p]
            if cur_node.node_type != NodeType.DIR:
                raise Exception("Error Node Type")

    def addContentToFile(self, filePath: str, content: str) -> None:
        path_list = filePath.split("/")
        file_name = path_list[-1]
        path_list = path_list[:-1]
        cur_node = self.dummy
        for p in path_list:
            if p not in cur_node.node_dict:
                raise Exception("No Exist Path")
            cur_node = cur_node.node_dict[p]
            if cur_node.node_type != NodeType.DIR:
                raise Exception("Error Node Type, not DIR")
        if file_name not in cur_node.node_dict:
            new_node = Node(file_name, NodeType.FILE)
            new_node.content = content
            cur_node.node_dict[file_name] = new_node
            return

        cur_node = cur_node.node_dict[file_name]
        if cur_node.node_type != NodeType.FILE:
            raise Exception("Error Node Type, not FILE")
        cur_node.content += content

    def readContentFromFile(self, filePath: str) -> str:
        path_list = filePath.split("/")
        file_name = path_list[-1]
        path_list = path_list[:-1]
        cur_node = self.dummy
        for p in path_list:
            if p not in cur_node.node_dict:
                raise Exception("No Exist Path")
            cur_node = cur_node.node_dict[p]
            if cur_node.node_type != NodeType.DIR:
                raise Exception("Error Node Type, not DIR")
        if file_name not in cur_node.node_dict:
            raise Exception("Not exist")
        cur_node = cur_node.node_dict[file_name]
        if cur_node.node_type != NodeType.FILE:
            raise Exception("Error Node Type, not FILE")
        return cur_node.content


class NodeType(Enum):
    FILE = 1
    DIR = 2


class Node:
    def __init__(self, dir_name, node_type):
        self.dir_name = dir_name
        self.node_type = node_type
        self.content = None
        self.node_dict = dict()
        if node_type == NodeType.FILE:
            self.node_dict = {dir_name: {}}

    def add_child(self, dir_name, node):
        self.node_dict[dir_name] = node

    def add_content(self, content):
        if self.node_type == NodeType.FILE:
            self.content = content
