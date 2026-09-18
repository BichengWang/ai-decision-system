from collections import defaultdict

SIZE_ORDER = ['small', 'middle', 'large']


class Package:
    def __init__(self, package_id, package_size):
        self.locker = None
        self.package_id = package_id
        self.package_size = package_size


class Locker:
    def __init__(self, locker_id, locker_size):
        self.locker_id = locker_id
        self.locker_size = locker_size


class AmazonLocker:
    def __init__(self, lockers):
        self.empty_dict = defaultdict(list)
        for locker in lockers:
            self.empty_dict[locker.locker_size].append(locker)
        self.stored_packages = dict()

    def pick_up(self, package_id):
        if package_id not in self.stored_packages:
            return None
        package = self.stored_packages[package_id]
        self.return_locker(package.locker)
        return package

    def store_package(self, package):
        locker = self.allocate_locker(package.package_size)
        if not locker:
            return None
        package.locker = locker
        self.stored_packages[package.package_id] = package
        return package.package_id

    def allocate_locker(self, req_size):
        for size in SIZE_ORDER:
            if size < req_size:
                continue
            if len(self.empty_dict[size]):
                locker = self.empty_dict[size].pop()
                return locker
        return None

    def return_locker(self, locker):
        self.empty_dict[locker.locker_size].append(locker)
        return


if __name__ == "__main__":
    lockers = [Locker('001', 'small'), Locker('002', 'small'), Locker('003', 'large'), Locker('004', 'middle')]
    a = AmazonLocker(lockers)
    p1 = Package("A", 'small')
    p2 = Package("B", 'large')
    p3 = Package("C", 'middle')
    p1_id = a.store_package(p1)
    p2_id = a.store_package(p2)
    p3_id = a.store_package(p3)
    print(a.pick_up(p1_id).package_id)
    print(a.pick_up(p2_id).package_id)
    print(a.pick_up(p3_id).package_id)