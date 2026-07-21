import requests
import os

try:
    from robot_descriptions._descriptions import DESCRIPTIONS, Format
except ImportError:
    DESCRIPTIONS = {}
    Format = None

TOKEN = os.environ.get("GITHUB_TOKEN", None)
OWNERS_REPOS = [("unitreerobotics", "unitree_ros")]

OUTPUT_DIR = "../data/raw/urdf/"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_urdf_files_from_repo(token, owner, repo):
    
    files_locations = []
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    repo_info_url = f"https://api.github.com/repos/{owner}/{repo}"
    repo_info_response = requests.get(repo_info_url, headers=headers)
    repo_info = repo_info_response.json()
    default_branch = repo_info.get("default_branch")

    if repo_info_response.status_code != 200 or not default_branch:
        print(f"Failed to read repo metadata for {owner}/{repo}: {repo_info.get('message', 'unknown error')}")
        return repo_info.get("license", {}).get("name", "Unknown"), [], []

    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    response = requests.get(url, headers=headers)
    tree = response.json()

    if response.status_code != 200 or "tree" not in tree:
        print(f"Failed to read tree for {owner}/{repo}: {tree.get('message', 'unknown error')}")
        return repo_info.get("license", {}).get("name", "Unknown"), [], []

    urdf_files = [
        item for item in tree["tree"]
        if item["type"] == "blob" and item["path"].endswith(".urdf")
    ]

    license = repo_info.get("license", {}).get("name", "Unknown")
    urls = []
    
    for item in urdf_files:
        file_path = item["path"]
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{file_path}"
        urls.append(raw_url)
        file_response = requests.get(raw_url, headers=headers)

        if file_response.status_code == 200:
            content = file_response.text
            local_path = os.path.join(OUTPUT_DIR, file_path.replace("/", "_"))
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Downloaded: {file_path}")
            files_locations.append(local_path)
        else:
            print(f"Failed ({file_response.status_code}): {file_path}")

    return license, urls, files_locations


MOBILE_TAGS = {"quadruped", "wheeled", "mobile_manipulator", "humanoid", "biped", "drone"}

# Filter only URDF robots with mobile tags AND allowlisted licenses
ALLOWED_LICENSES = {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "CC-BY-4.0", "CC-BY"}

SELECTED_ROBOTS = [
    name for name, desc in DESCRIPTIONS.items()
    if Format is not None
    and Format.URDF in desc.formats
    and MOBILE_TAGS.intersection(desc.tags)
    and desc.license_spdx in ALLOWED_LICENSES
]

def get_urdf_files_from_robot_descriptions(token, robot_names: list = SELECTED_ROBOTS, max_files: int = 100):
    if not DESCRIPTIONS or Format is None:
        print("robot_descriptions unavailable, skipping robot_descriptions collection")
        return [], [], []

    all_licenses   = []
    all_urls       = []
    all_file_paths = []
    total_downloaded = 0

    repos_to_robots = {}
    for robot_name in robot_names:
        desc = DESCRIPTIONS.get(robot_name)
        if desc is None:
            continue
        repo = desc.repository
        if repo not in repos_to_robots:
            repos_to_robots[repo] = []
        repos_to_robots[repo].append((robot_name, desc))

    print(f"Selected {len(robot_names)} robots across {len(repos_to_robots)} repositories from robot_descriptions")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    for repo, robots in repos_to_robots.items():
        if total_downloaded >= max_files:
            print(f"Reached {max_files} files limit, stopping")
            break

        search_url = f"https://api.github.com/search/repositories?q={repo}+in:name"
        search_resp = requests.get(search_url, headers=headers).json()
        items = search_resp.get("items", [])

        if not items:
            print(f"  Could not find owner for repo: {repo}, skipping")
            continue

        best      = max(items, key=lambda x: x.get("stargazers_count", 0))
        owner     = best["owner"]["login"]
        full_name = best["full_name"]
        print(f"\nRepo: {full_name} (for robots: {[r[0] for r in robots]})")

        license_name, urls, file_paths = get_urdf_files_from_repo(token, owner, repo)

        for path, url in zip(file_paths, urls):
            if total_downloaded >= max_files:
                print(f"  Reached {max_files} files limit mid-repo, stopping")
                break
            all_licenses.append(license_name)
            all_urls.append(url)
            all_file_paths.append(path)
            total_downloaded += 1

    print(f"\nTotal downloaded: {total_downloaded} URDF files")
    return all_licenses, all_urls, all_file_paths
