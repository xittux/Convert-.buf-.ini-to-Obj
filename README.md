# Convert-.buf-.ini-to-Obj
<img width="1913" height="480" alt="image" src="https://github.com/user-attachments/assets/17d520cb-f74e-4fbe-916c-b4d74fbb2537" />

BUF & INI to OBJ Converter (Python)

A Python-based converter that transforms .buf and .ini files into Wavefront .obj 3D models.

⚠️ Version 1 – Early Release
This is the first public version of the project. Some features are still incomplete and may not work as expected.

Overview

This tool parses:

.buf files for raw mesh data (vertices, indices, normals, UVs depending on structure)

.ini files for configuration and structural metadata

It reconstructs the mesh and exports it to the .obj format, making it compatible with common 3D software.

Current Status (V1)

The core mesh reconstruction works, including:

Vertex positions

Face indices

Basic geometry export

However, there are known issues:

UV coordinates may not be fully accurate

Textures do not automatically load in Blender

Material (.mtl) generation may be incomplete or missing

<img width="721" height="860" alt="image" src="https://github.com/user-attachments/assets/8aeef9e2-98ab-4334-a1bb-e9d14070ae30" />

<img width="1919" height="843" alt="image" src="https://github.com/user-attachments/assets/2c00da4b-04bb-4bac-a841-16da178450a9" />



Some meshes may require manual adjustment after import

This version focuses mainly on geometry extraction. Texture mapping support is still being improved.
