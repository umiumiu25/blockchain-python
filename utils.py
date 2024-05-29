import collections
import logging
import re
import socket

logger = logging.getLogger(__name__)

RE_IP = re.compile(
    "(?P<prefix_host>^\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.)(?P<last_ip>\\d{1,3}$)"
)


def sorted_dict_by_key(unsorted_dict):
    return collections.OrderedDict(sorted(unsorted_dict.items(), key=lambda d: d[0]))


def pprint(chains):
    for i, chain in enumerate(chains):
        print(f'{"=" * 25} Chain {i} {"=" * 25}')
        for key, value in chain.items():
            if key == "transactions":
                print(f"{key:40}:")
                for transaction in value:
                    print(f'{"-" * 15}')
                    for k, v in transaction.items():
                        print(f"{k:40}: {v}")
            else:
                print(f"{key:40}: {value}")
    print("*" * 60)


def is_found_host(target, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            sock.connect((target, port))
            return True
        except Exception as e:
            logger.error(
                {
                    "action": "is_found_host",
                    "target": target,
                    "port": port,
                    "error": e,
                }
            )
            return False


def find_neighbors(
    my_host, my_port, start_ip_range, end_ip_range, start_port, end_port
):
    address = f"{my_host}:{my_port}"
    m = RE_IP.match(my_host)
    if not m:
        return None

    prefix_host = m.group("prefix_host")
    last_ip = m.group("last_ip")

    neighbors = []
    for guess_port in range(start_port, end_port):
        for ip_range in range(start_ip_range, end_ip_range):
            guess_host = f"{prefix_host}{int(last_ip)+int(ip_range)}"
            guess_address = f"{guess_host}:{guess_port}"
            if is_found_host(guess_host, guess_port) and not guess_address == address:
                neighbors.append(guess_address)
    return neighbors


def get_host():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception as e:
        logger.debug({"action": "get_host", "error": e})
        return "127.0.0.1"


if __name__ == "__main__":
    # print(is_found_host("127.0.0.1", 5001))
    # print(find_neighbors("192.168.68.52", 5001, 0, 3, 5001, 5004))
    print(get_host())
