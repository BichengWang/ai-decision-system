class FileType(object):
    DIR = 0
    FILE = 1


class Node(object):
    def __init__(self, name, type):
        self.name = name
        self.type = type
        self.child = dict()
        self.content = ""


class FileSystem(object):
    def __init__(self):
        self.root = Node("", FileType.DIR)

    def _find_node(self, path):
        cur = self.root
        if path == "/" or path == "":
            return cur
        path_s = path.split("/")
        for s in path_s:
            if s == "":
                continue
            if cur.type != FileType.DIR or s not in cur.child:
                return None
            cur = cur.child[s]
        return cur

    def ls(self, path):
        """
        :type path: str
        :rtype: List[str]
        """
        cur = self._find_node(path)
        if not cur:
            return []
        ret = []
        for _,v in cur.child.items():
            ret.append(v.name)
        return ret

    def mkdir(self, path):
        """
        :type path: str
        :rtype: None
        """
        print("mkdir start")
        cur = self.root
        if path == "/" or path == "":
            return
        path_s = path.split("/")
        print(path_s)
        for s in path_s:
            print(s)
            if s == "":
                continue
            if cur.type != FileType.DIR:
                return
            if s not in cur.child:
                cur.child[s] = Node(s, FileType.DIR)
            cur = cur.child[s]
        print("mkdir done")
        return

    def addContentToFile(self, filePath, content):
        """
        :type filePath: str
        :type content: str
        :rtype: None
        """
        print("addContentToFile start")
        idx = filePath.rfind("/")
        cur = self._find_node(filePath[:idx])
        if not cur or cur.type != FileType.DIR:
            return
        file_name = filePath[idx + 1:]
        new_node = Node(file_name, FileType.FILE)
        new_node.content = content
        cur.child[file_name] = new_node

        print("addContentToFile done")

    def readContentFromFile(self, filePath):
        """
        :type filePath: str
        :rtype: str
        """

        print("readContentFromFile start")
        cur = self._find_node(filePath)
        print("readContentFromFile done")
        return cur.content if cur and cur == FileType.FILE else ""

if __name__ == "__main__":
    fs = FileSystem()
    print(fs.ls("/"))
    fs.mkdir("/a/b/c")
    fs.addContentToFile("/a/b/c/d", "hello")
    print(fs.ls("/"))
    print(fs.readContentFromFile("/a/b/c/d"))
    fs.addContentToFile("/a/b/c/d", "hello hello world")
