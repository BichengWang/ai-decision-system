import os


def index_files(root_dir):
    """Creates an index of all filenames (including nested folders) in the given root directory."""
    file_index = {}
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            file_index[filename.lower()] = file_path
    return file_index


def search_file(file_index, keyword):
    """Searches for a file using a keyword (case-insensitive)."""
    keyword = keyword.lower()
    results = {name: path for name, path in file_index.items() if keyword in name}
    return results


# Example usage
if __name__ == "__main__":
    roots = ["D:/"]
    file_index = {}
    for root_directory in roots:
        file_index.update(index_files(root_directory))

    while True:
        keyword = input("Enter keyword to search: ")
        search_results = search_file(file_index, keyword)
        if search_results:
            print("Found the following files:")
            for name, path in search_results.items():
                print(f"{name} -> {path}")
        else:
            print("No files found matching the keyword.")