import numpy as np
import traitlets
from yt.data_objects.data_containers import YTDataContainer
from yt.data_objects.construction_data_containers import YTProj
from yt.data_objects.selection_objects.slices import YTSlice, YTCuttingPlane
from yt_idv.opengl_support import Texture2D, VertexArray, VertexAttribute
from yt_idv.scene_data.base_data import SceneData
from OpenGL import GL

class BasePlane(SceneData):
    """
    base class for a plane.

    """
    name = "image_plane_data"

    # calculated or sterilized:
    plane_normal = None
    plane_pt = None
    east_vec = None
    north_vec = None

    # shader-related objects
    texture_object = traitlets.Instance(Texture2D)
    texture_id = traitlets.CInt()
    size = traitlets.CInt(-1)

    # required arguments
    normal = traitlets.Instance(np.ndarray, allow_none=False)
    center = traitlets.Instance(np.ndarray, allow_none=False)
    data = traitlets.Instance(np.ndarray, allow_none=False)
    width = traitlets.Float(allow_none=False)
    height = traitlets.Float(allow_none=False)


    def _set_plane(self):

        # set the in-plane coordinate vectors, basis_u = east, basis_v = north
        unit_normal = self.normal / np.linalg.norm(self.normal)
        if self.east_vec is None or self.north_vec is None:
            if unit_normal[0] == 0 and unit_normal[1] == 0:
                east_vec = np.array([1., 0., 0.])
                north_vec = np.array([0., 1., 0.])
            elif unit_normal[1] == 0 and unit_normal[2] == 0:
                east_vec = np.array([0., 1., 0.])
                north_vec = np.array([0., 0., 1.])
            elif unit_normal[0] == 0 and unit_normal[2] == 0:
                east_vec = np.array([1., 0., 0.])
                north_vec = np.array([0., 0., 1.])
            else:
                raise ValueError("It looks like your plane is not normal to an axis, please"
                                 " set east_vec and north_vec before calling add_data().")
        else:
            east_vec = self.east_vec
            north_vec = self.north_vec

        # homogenous scaling matrix from UV texture coords to in-plane coords
        scale = np.eye(4)
        scale[0, 0] = self.width
        scale[1, 1] = self.height

        # homogenous projection matrix from in-plane coords to world at origin
        to_world = np.eye(4)
        to_world[0:3, 0] = east_vec
        to_world[0:3, 1] = north_vec
        to_world[0:3, 2] = unit_normal

        # homogenous translation matrix
        translate = np.eye(4)
        translate[0:3, 3] = self.center

        # combined homogenous projection matrix
        self.to_worldview = np.matmul(translate, np.matmul(to_world, scale))

        if type(self.data_source) == YTCuttingPlane:
            # the cutting plane "center" is actually not the true center. So here,
            # we apply our current projection matrix to the center texture coordinates
            # to get the true center of our cutting plane. We then add an additional
            # translation to our to_worldview matrix to get from the cutting plane
            # "center" to the true center
            true_center = np.matmul(self.to_worldview, np.array([0.5, 0.5, 0., 1.]).T)
            extra_translate = np.eye(4)
            extra_translate[0:3, 3] = self.center - true_center[0:3]
            self.to_worldview = np.matmul(extra_translate, self.to_worldview)

        self.to_worldview = self.to_worldview.astype("f4")

    def add_data(self):

        self._set_plane()
        # our in-plane coordinates. same as texture coordinates
        verts = np.array([
            [1, 0],
            [0, 0],
            [0, 1],
            [1, 1]
        ])

        i = np.array([
            [0, 1, 2],
            [0, 2, 3]
        ])
        i.shape = (i.size, 1)

        self.vertex_array.attributes.append(
            VertexAttribute(name="model_vertex", data=verts.astype("f4"))
        )

        self.vertex_array.indices = i.astype("uint32")
        self.size = i.size
        self.build_textures()

    @traitlets.default("vertex_array")
    def _default_vertex_array(self):
        return VertexArray(name="simple_slice", each=0)

    def build_textures(self):
        tex_id = GL.glGenTextures(1)
        bitmap = self.data.astype("f4")
        texture = Texture2D(
            texture_name=tex_id, data=bitmap, boundary_x="clamp", boundary_y="clamp"
        )
        self.texture_id = tex_id
        self.texture_object = texture


class PlaneData(BasePlane):
    """
    a 2D plane built from a yt slice, cutting plane or projection
    """
    data_source = traitlets.Instance(YTDataContainer)

    def add_data(self, field, width, frb_dims=(400, 400), translate=0.):

        # set our image plane data
        frb = self.data_source.to_frb(width, resolution=frb_dims)
        self.data = frb[field]
        dstype = type(self.data_source)
        if dstype == YTSlice:
            normal = np.zeros((3,))
            normal[self.data_source.axis] = 1.
            center = np.zeros((3,))
            center[self.data_source.axis] = self.data_source.coord
        elif dstype == YTCuttingPlane:
            self.north_vec = self.data_source.orienter.north_vector
            self.north_vec = self.north_vec / np.linalg.norm(self.north_vec)
            normal = self.data_source.orienter.normal_vector
            normal = normal / np.linalg.norm(normal)  # make sure it's a unit normal
            self.east_vec = np.cross(normal, self.north_vec)
            center = self.data_source.center.value
        elif isinstance(self.data_source, YTProj):
            normal = np.zeros((3,))
            normal[self.data_source.axis] = 1.
            center = np.zeros((3,))
            center[self.data_source.axis] = 1.
        else:
            raise ValueError(f"Unexpected data_source type. data_source must be one of"
                             f" YTSlice or YTproj but found {dstype}.")

        if translate != 0:
            center += translate * normal

        self.center = center
        self.normal = normal
        self.width = width
        self.height = width

        super().add_data()

