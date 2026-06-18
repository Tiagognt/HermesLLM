# Replication of the EMOS Robot resume approach
# Since we have the original structure, no LLM calls are needed
# We just have to parse the URDF to only keep the relevant information translated into natural language

import xml.etree.ElementTree as ET
import collector as col



def format_urdf(file_path):
    # Load and parse the XML file
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Ensure it's actually a URDF
    if root.tag != 'robot':
        raise ValueError("Invalid URDF: Root tag is not 'robot'")
    
    final_text = ""
    robot_name = root.attrib.get('name', 'Unknown Robot')
    final_text += f"This document details the physical specifications for the {robot_name} extracted from its URDF description."

    # 1. Extract Links information
    final_text += "The robot consists of the following links with their respective physical properties: "
    for link in root.findall('link'): 
        link_name = link.attrib.get('name')
        
        # Check if it has inertial properties (mass, center of mass, inertia moments and products)
        mass_tag = link.find('.//inertial/mass')
        mass = mass_tag.attrib.get('value') if mass_tag is not None else "Unknown"
        com_tag = link.find('.//inertial/origin')
        com = com_tag.attrib.get('xyz') if com_tag is not None else "Unknown"
        inertia_tag = link.find('.//inertial/inertia')
        inertia = {
            'ixx': inertia_tag.attrib.get('ixx') if inertia_tag is not None else "Unknown",
            'ixy': inertia_tag.attrib.get('ixy') if inertia_tag is not None else "Unknown",
            'ixz': inertia_tag.attrib.get('ixz') if inertia_tag is not None else "Unknown",
            'iyy': inertia_tag.attrib.get('iyy') if inertia_tag is not None else "Unknown",
            'iyz': inertia_tag.attrib.get('iyz') if inertia_tag is not None else "Unknown",
            'izz': inertia_tag.attrib.get('izz') if inertia_tag is not None else "Unknown"
        }
        
        final_text += f" The link named {link_name} has a mass of {mass}. It has a center of mass located at the following xyz coordinates: {com}. Its inertia moments are Ixx: {inertia['ixx']}, Iyy: {inertia['iyy']}, Izz: {inertia['izz']}, and its inertia products are Ixy: {inertia['ixy']}, Ixz: {inertia['ixz']}, Iyz: {inertia['iyz']}. "

    # 2. Extract Joints
    final_text += "The robot has the following joints connecting all the previous listed links: "
    for joint in root.findall('joint'):
        joint_name = joint.attrib.get('name')
        joint_type = joint.attrib.get('type')
        
        # Get Parent and Child links
        parent = joint.find('parent').attrib.get('link') if joint.find('parent') is not None else "None"
        child = joint.find('child').attrib.get('link') if joint.find('child') is not None else "None"
        limit_tag = joint.find('limit')
        limits = {
            'lower': limit_tag.attrib.get('lower') if limit_tag is not None else "Unknown",
            'upper': limit_tag.attrib.get('upper') if limit_tag is not None else "Unknown",
            'effort': limit_tag.attrib.get('effort') if limit_tag is not None else "Unknown",
            'velocity': limit_tag.attrib.get('velocity') if limit_tag is not None else "Unknown"
        }
        axis_tag = joint.find('axis')
        axis = axis_tag.attrib.get('xyz') if axis_tag is not None else "Unknown"
        origin_tag = joint.find('origin')
        origin_position = origin_tag.attrib.get('xyz') if origin_tag is not None else "Unknown"
        origin_rotation = origin_tag.attrib.get('rpy') if origin_tag is not None else "Unknown"
        final_text += f" The joint named {joint_name} is of type {joint_type}. It connects the parent link {parent} to the child link {child}. The joint has the following limits: lower: {limits['lower']}, upper: {limits['upper']}, effort: {limits['effort']}, velocity: {limits['velocity']}. The axis of rotation is aligned with the vector {axis}. The origin relative position of the child link relative to the parent link is located at the following position and rotation: xyz: {origin_position}, rpy: {origin_rotation}. "
    
    return final_text

    
repo_texts = {}
for owner, repo in col.OWNERS_REPOS:
    # 1. Initialize the dictionary key for this specific repo
    repo_name = f"{owner}/{repo}"
    repo_texts[repo_name] = []
    
for owner, repo in col.OWNERS_REPOS:
    license, urls, urdf_files = col.get_urdf_files_from_repo(col.TOKEN, owner, repo)
    print(f"Found {len(urdf_files)} URDF files in {owner}/{repo}")
    for urdf_file in urdf_files:
        text = format_urdf(urdf_file)
        repo_texts[f"{owner}/{repo}"].append((text, license, urls[urdf_files.index(urdf_file)]))

repo_texts["robot_descriptions/urdf_files_dataset"] = []
licenses, urls, urdf_files = col.get_urdf_files_from_robot_descriptions(col.TOKEN)
print(f"Found {len(urdf_files)} URDF files from robot_descriptions")
for i, urdf_file in enumerate(urdf_files):
    try:
        text = format_urdf(urdf_file)
        repo_texts["robot_descriptions/urdf_files_dataset"].append((text, licenses[i], urls[i]))
    except Exception as e:
        print(f"  Failed to parse {urdf_file}: {e}")