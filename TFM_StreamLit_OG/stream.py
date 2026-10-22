import asyncio
import io

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
import tifffile
from PIL import Image, ImageDraw
from skimage.registration import optical_flow_ilk
from tqdm import tqdm
from traction_force.displacement import (
    RigidShift,
    Surface,
    dft_displacement,
    elastix_3d,
    elastix_displacement,
    rigid_shift_pcc,
)
from traction_force.force import tract
from traction_force.plot import plot_dis_vec


def get_rectangle_coords(coordinates: tuple) -> tuple:
    """Normalize coordinates so top-left < bottom-right regardless of drag direction."""
    point1, point2 = coordinates
    x1 = min(point1[0], point2[0])
    y1 = min(point1[1], point2[1])
    x2 = max(point1[0], point2[0])
    y2 = max(point1[1], point2[1])
    return (x1, y1, x2, y2)


def numpy_to_pil_uint8(img):
    """Converts numpy to uint8 image file

    Args:
        img (ndarray): numpy array

    Returns:
        _type_: image
    """
    img = np.asarray(img)

    if img.dtype.kind == "f":
        img = img - np.nanmin(img)
        if np.nanmax(img) > 0:
            img = img / np.nanmax(img)
        img = (img * 255).astype(np.uint8)
    elif img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)

    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)

    return Image.fromarray(img)


async def run_dft():
    """Runs dft_displacement on all frames in before_img against after_img and stores results in displacementList."""
    st.session_state.displacementList.clear()
    moving = st.session_state.before_img
    fixed = st.session_state.after_img
    if moving is not None:
        for frame in moving:
            st.session_state.displacementList.append(
                dft_displacement(frame, fixed, half_window_size, step_size)[0]
            )
            with st.empty():  # Add a small delay to allow Streamlit to update the UI
                st.write(
                    f"Processed frame {len(st.session_state.displacementList)} of {len(moving)}"
                )


async def run_elastix():
    """Runs elastix_displacement on all frames in before_img against after_img and stores results in displacementList."""
    st.session_state.displacementList.clear()
    moving = st.session_state.before_img
    fixed = st.session_state.after_img
    if moving is not None:
        for frame in moving:
            st.session_state.displacementList.append(
                elastix_displacement(fixed, frame, half_window_size, step_size)
            )


async def run_optical_flow():
    """Runs dft_displacement on all frames in before_img against after_img and stores results in displacementList."""
    st.session_state.displacementList.clear()
    moving = st.session_state.before_img
    fixed = st.session_state.after_img
    if moving is not None:
        for frame in moving:
            frame_norm = (frame - np.min(frame)) / (
                np.max(frame) - np.min(frame) + 1e-10
            )
            fixed_norm = (fixed - np.min(fixed)) / (
                np.max(fixed) - np.min(fixed) + 1e-10
            )

            # Convert to float32 for better precision
            frame_norm = frame_norm.astype(np.float32)
            fixed_norm = fixed_norm.astype(np.float32)

            dis = optical_flow_ilk(frame_norm, fixed_norm, radius=r)
            dis = np.stack(
                [dis[1], dis[0]], axis=-1
            )  # Swap axes to match expected format
            st.session_state.displacementList.append(dis)
            print(dis.shape, r)


async def run_elastix3d():
    """Runs elastix_3d on all frames in before_img against after_img and stores results in displacementList."""
    st.session_state.displacementList.clear()
    if st.session_state.before_img is None or st.session_state.after_img is None:
        st.error("Please upload both Before (timelapse) and After images first.")

    elif st.session_state.dims["xyzct"]:
        fixed = st.session_state.after_img  # 2D array (reference)

        # Get all frames from before image
        displacement_list = []
        num_frames = st.session_state.before_img.shape[0]
        for frame_idx in tqdm(
            range(num_frames), desc="Elastix Processing", unit="frame"
        ):
            frame_data = st.session_state.before_img[frame_idx]
            moving = frame_data

            dis = elastix_3d(
                moving,
                fixed,
                "bspline_tfm.txt",
                step_size,
                step_size,
                9,
            )
            st.write(st.session_state.surf)
            displacement_list.append(dis)
            st.session_state.displacementList.append(dis)  # Store in session state
            st.info(f"✅ Frame {frame_idx + 1}/{num_frames} processed.")

            # Store the full list
            st.session_state.displacementList = displacement_list
            # st.session_state.displacement = displacement_list[-1]  # Last frame as default
            st.success(f"✅ Elastix completed for all {num_frames} frames.")

    elif st.session_state.dims["xyz"]:
        with st.spinner("Processing with Elastix..."):
            fixed = st.session_state.after_img
            moving = st.session_state.before_img
            dis = elastix_3d(moving, fixed, "bspline_tfm.txt", step_size, step_size, 9)
            st.session_state.displacementList.append(dis)


if __name__ == "__main__":
    st.title("Traction Force Microscopy")

    before = st.file_uploader("Before Image")
    after = st.file_uploader("After Image")
    col1, col2 = st.columns(2, vertical_alignment="bottom")

    # Define session states
    if "displacement" not in st.session_state:
        st.session_state.displacement = None
    if "error" not in st.session_state:
        st.session_state.error = None
    if "position" not in st.session_state:
        st.session_state.position = None
    if "before_img" not in st.session_state:
        st.session_state.before_img = None
    if "after_img" not in st.session_state:
        st.session_state.after_img = None
    if "fig" not in st.session_state:
        st.session_state.fig = None
    if "mode" not in st.session_state:
        st.session_state.mode = None
    if "traction" not in st.session_state:
        st.session_state.traction = None
    if "displacementList" not in st.session_state:
        st.session_state.displacementList = []
    if "tractionList" not in st.session_state:
        st.session_state.tractionList = []
    if "opticalflow" not in st.session_state:
        st.session_state.opticalflow = False
    if "current_frame" not in st.session_state:
        st.session_state.current_frame = None
    if "roi_shape" not in st.session_state:
        st.session_state.roi_shape = None
    if "check_crop" not in st.session_state:
        st.session_state.check_crop = False
    if "surf" not in st.session_state:
        st.session_state.surf = None
    if "before_all" not in st.session_state:
        st.session_state.before_all = None
    if "ElastixCheck" not in st.session_state:
        st.session_state.ElastixCheck = False
    if "coordinates" not in st.session_state:
        st.session_state.coordinates = False

    # Add this to your app (e.g., after file upload)
    st.markdown("### 📊 Select Image Dimensionality")

    # Initialize session state for dimensions
    if "dims" not in st.session_state:
        st.session_state.dims = {
            "xy": False,
            "xyz": False,
            "xyzt": False,
            "xyzc": False,
            "xyzct": False,
            "xyt": False,
        }

    # Define dimension options
    dim_options = {
        "xy": "2D (x, y)",
        "xyz": "3D (x, y, z)",
        #'xyzt': '4D (x, y, z, t)',
        #'xyzc': '4D (x, y, z, c)',
        "xyzct": "4D (x, y, z, c, t)",
        #'xyzt': '4D (x, y, z, t)',
        "xyt": "3D (x, y, t)",
    }

    # Use checkboxes
    selected_dims = {}
    for key, label in dim_options.items():
        selected_dims[key] = st.checkbox(
            label, value=st.session_state.dims.get(key, False)
        )

    # Update session state
    st.session_state.dims = selected_dims
    # Show uploaded images

    # Before image
    with col1:
        if before is not None:
            img = tifffile.TiffFile(before).asarray()
            st.session_state.before_all = img

            if True not in st.session_state.dims.values() and before is not None:
                st.markdown("# :red[**Please choose a dimension.**]")

            elif st.session_state.dims["xyt"]:
                st.success(f"Loaded timelapse with {img.shape[0]} frames!")
                frame_idx = st.slider("Select frame:", 0, img.shape[0] - 1, 0)
                frame_data = img[frame_idx]
                st.image(
                    numpy_to_pil_uint8(frame_data),
                    caption=f"Before Frame {frame_idx + 1} of {img.shape[0]}",
                )
                st.session_state.before_img = img
                st.session_state.current_frame = frame_data
            elif st.session_state.dims["xy"]:
                st.session_state.before_img = np.array([img])
                st.image(img, caption="Before Image")
                st.session_state.current_frame = st.session_state.before_img
            elif st.session_state.dims["xyz"]:
                st.success(f"Loaded Z-stack with {img.shape[0]} frames!")
                frame_idx = st.slider("Select slice:", 0, img.shape[0] - 1, 0)
                frame_data = img[frame_idx]
                frame_data = (frame_data - frame_data.min()) / (
                    frame_data.max() - frame_data.min() + 1e-8
                )
                frame_data *= 255
                st.image(
                    Image.fromarray(frame_data.astype(np.uint8)),
                    caption=f"Before Frame {frame_idx + 1} of {img.shape[0]}",
                )
                st.session_state.before_img = img
            elif st.session_state.dims["xyzct"]:
                st.success(f"Loaded Z-stack with {img.shape[0]} frames!")
                frame_idx = st.slider("Select frame:", 0, img.shape[0] - 1, 0)
                slice_idx = st.slider("Select slice:", 0, img.shape[1] - 1, 0)
                channel_idx = st.slider("Select channel:", 0, img.shape[2] - 1, 0)
                frame_data = img[frame_idx][slice_idx][channel_idx]
                # frame_data = (frame_data-frame_data.min())/(frame_data.max()-frame_data.min()+1e-8)
                # frame_data *= 255
                st.image(
                    numpy_to_pil_uint8(frame_data),
                    caption=f"Before Frame {frame_idx + 1} of {img.shape[0]}",
                )
                st.session_state.before_img = img[:, :, 0, :, :]
                st.session_state.current_frame = frame_data
        else:
            st.session_state.before_img = None

    # After image
    with col2:
        if after is not None and before is not None:
            img = tifffile.TiffFile(after).asarray()
            if len(img.shape) == 2:
                st.session_state.after_img = img
                st.image(numpy_to_pil_uint8(img), caption="Reference Frame")
            elif len(img.shape) == 3:
                st.success(f"Loaded Z-stack with {img.shape[0]} frames!")
                frame_idx = st.slider(
                    "Select After Image slice:", 0, img.shape[0] - 1, 0
                )
                frame_data = img[frame_idx]
                # frame_data = (frame_data-frame_data.min())/(frame_data.max()-frame_data.min()+1e-8)
                # frame_data *= 255
                st.image(
                    numpy_to_pil_uint8(frame_data),
                    caption=f"Before Frame {frame_idx + 1} of {img.shape[0]}",
                )
                st.session_state.after_img = img
                if st.session_state.before_img is not None:
                    before_surface = Surface(st.session_state.before_img[0])
                    after_surface = Surface(img)
                    st.session_state.surf = (before_surface + after_surface) // 2
            else:
                st.error("Illegal image dimension.")
            if (
                st.session_state.dims["xyzct"]
                and st.session_state.before_img is not None
            ):
                before_surface = Surface(st.session_state.before_img[0])
                after_surface = Surface(st.session_state.after_img)

    # Select ROI
    # with st.expander('🌾Crop Image'):
    if True:
        st.session_state.check_crop = st.checkbox("Crop Image", value=False)
        if st.session_state.current_frame is not None and st.session_state.check_crop:
            img = st.session_state.current_frame
            st.write(img.shape)
            x0 = st.number_input(
                "X coordinate",
                min_value=0,
                max_value=img.shape[1],
                value=img.shape[1] // 3,
            )
            y0 = st.number_input(
                "Y Coordinate",
                min_value=0,
                max_value=img.shape[0],
                value=img.shape[0] // 3,
            )
            h = st.number_input(
                "Height",
                min_value=1,
                max_value=img.shape[0] - y0,
                value=img.shape[0] // 4,
            )
            w = st.number_input(
                "Width",
                min_value=1,
                max_value=img.shape[1] - x0,
                value=img.shape[1] // 4,
            )
            st.image(numpy_to_pil_uint8(img[y0 : y0 + h, x0 : x0 + w]))
            st.session_state.roi_shape = {"x0": x0, "y0": y0, "h": h, "w": w}

            pil_image = numpy_to_pil_uint8(img)

            draw = ImageDraw.Draw(pil_image)

            # Enlarge the rectangle selected between point1 and point2
            if st.session_state["coordinates"]:
                coords = get_rectangle_coords(st.session_state["coordinates"])
                new_image = pil_image.crop(coords)
                new_image = new_image.resize(
                    (int(new_image.width * 1.5), int(new_image.height * 1.5))
                )
                st.image(new_image, width="content")

            if (
                st.session_state.dims["xyt"]
                and st.session_state.before_img is not None
                and st.session_state.after_img is not None
            ):
                before_tmp = st.session_state.before_img[:, y0 : y0 + h, x0 : x0 + w]
                after_tmp = st.session_state.after_img[y0 : y0 + h, x0 : x0 + w]
                uy, ux = RigidShift(before_tmp[0], after_tmp, h // 5)
                st.write(f"Rigid shift is y:{float(uy)} x:{float(ux)}")
                uy, ux = round(uy), round(ux)
                uuy, uux = rigid_shift_pcc(
                    st.session_state.after_img[
                        y0 + uy : y0 + uy + h, x0 + ux : x0 + ux + w
                    ],
                    before_tmp[0],
                )
                st.write(
                    f"Rigid shift second iteration is y:{float(uuy)} x:{float(uux)}"
                )
                uuy, uux = round(uuy), round(uux)
                st.session_state.before_img = st.session_state.before_img[
                    :, y0 : y0 + h, x0 : x0 + w
                ]
                st.session_state.after_img = st.session_state.after_img[
                    y0 + uy + uuy : y0 + uy + uuy + h, x0 + ux + uux : x0 + ux + uux + w
                ]

            if (
                st.session_state.dims["xy"]
                and st.session_state.before_img is not None
                and st.session_state.after_img is not None
            ):
                before_tmp = st.session_state.before_img[y0 : y0 + h, x0 : x0 + w]
                after_tmp = st.session_state.after_img[y0 : y0 + h, x0 : x0 + w]
                uy, ux = RigidShift(before_tmp, after_tmp, h // 5)
                st.write(f"Rigid shift is y:{float(uy)} x:{float(ux)}")
                uy, ux = round(uy), round(ux)
                uuy, uux = rigid_shift_pcc(
                    st.session_state.after_img[
                        y0 + uy : y0 + uy + h, x0 + ux : x0 + ux + w
                    ],
                    before_tmp,
                )
                st.write(
                    f"Rigid shift second iteration is y:{float(uuy)} x:{float(uux)}"
                )
                uuy, uux = round(uuy), round(uux)
                st.session_state.before_img = st.session_state.before_img[
                    y0 : y0 + h, x0 : x0 + w
                ]
                st.session_state.after_img = st.session_state.after_img[
                    y0 + uy + uuy : y0 + uy + uuy + h, x0 + ux + uux : x0 + ux + uux + w
                ]

            if (
                st.session_state.dims["xyzct"]
                and st.session_state.before_img is not None
                and st.session_state.after_img is not None
            ):
                st.session_state.before_img = st.session_state.before_img[
                    :, :, y0 : y0 + h, x0 : x0 + w
                ]
                after_img_tmp = st.session_state.after_img[:, y0 : y0 + h, x0 : x0 + w]
                before_surface = Surface(st.session_state.before_img[0])
                after_surface = Surface(after_img_tmp)
                uy, ux = RigidShift(
                    st.session_state.before_img[0][before_surface],
                    after_img_tmp[after_surface],
                    h // 3,
                )
                st.write(f"Rigid shift first iteration is y:{float(uy)} x:{float(ux)}")
                uy, ux = round(uy), round(ux)
                uuy, uux = rigid_shift_pcc(
                    st.session_state.after_img[after_surface][
                        y0 + uy : y0 + uy + h, x0 + ux : x0 + ux + w
                    ],
                    st.session_state.before_img[0][before_surface],
                )
                st.write(
                    f"Rigid shift second iteration is y:{float(uuy)} x:{float(uux)}"
                )
                uuy, uux = round(uuy), round(uux)
                st.session_state.after_img = st.session_state.after_img[
                    :,
                    y0 + uy + uuy : y0 + uy + uuy + h,
                    x0 + ux + uux : x0 + ux + uux + w,
                ]
                st.image(numpy_to_pil_uint8(st.session_state.after_img[after_surface]))

    col3, col4 = st.columns(2)
    # Slider for step size and window size
    with col3:
        st.markdown("### Half Window Size")
        half_window_size = st.slider(
            "Half Window Size (pixels)",
            min_value=4,
            max_value=128,
            value=10,
            step=1,
            help="Size of the window used for displacement calculation. Larger windows are more robust but less precise.",
        )

    with col4:
        st.markdown("### Step Size")
        step_size = st.slider(
            "Step Size (pixels)",
            min_value=1,
            max_value=128,
            value=10,
            step=1,
            help="Step size between windows. Smaller steps give higher resolution but take longer to compute.",
        )

    mode = st.radio("Select a mode:", ("magnitude", "field", "both"))

    col4_5, col4_6, col4_7, col4_8 = st.columns(4)
    with col4_7:
        r = st.number_input("Radius for Optical Flow in px", value=30, step=1)

    col5, col6, col7, col8 = st.columns(4)
    # Displacement Calculations
    with col5:
        if st.button("Run DFT on All Frames", type="primary"):
            with st.spinner("Processing all frames with DFT..."):
                asyncio.run(run_dft())

    with col6:
        if st.button("Run Elastix on All Frames", type="primary"):
            with st.spinner("Processing all frames with Elastix..."):
                asyncio.run(run_elastix())

    with col7:
        if st.button("Run Optical Flow on All Frames (Parallel)", type="primary"):
            with st.spinner("Processing all frames with Optical Flow..."):
                asyncio.run(run_optical_flow())

    with col8:
        if st.button("Run Elastix for 3D", type="primary"):
            with st.spinner("Processing all frames with Elastix 3D..."):
                asyncio.run(run_elastix3d())

    col7, col8, col9, col10, col11, col12, col13 = st.columns(7)
    with col7:
        mue2pix = st.number_input(
            "Micrometer to Pixel Ratio", step=0.0001, format="%.4f", value=0.0772
        )
    with col8:
        E = st.number_input("Youngs Modolus in Pa", value=1200, step=1)
    with col9:
        nu = st.number_input("Poisson's Ration", value=0.49, step=0.01)
    with col10:
        alpha0 = st.number_input(
            "Initial Alpha Value:", value=1e-15, step=1e-15, format="%.15g"
        )
    with col11:
        h = st.number_input("Gel Height in Micrometer:\n", value=60, step=1)
    with col12:
        z = st.number_input("Image Height in Micrometer:\n", value=60, step=1)
    with col13:
        d = st.number_input("Dimensions of Image Stacks: ", value=2, step=1)

    with st.spinner("Plotting Displacements..."):
        if len(st.session_state.displacementList) > 1:
            with st.expander(
                "📊 View Displacement Field (Select Frame)", expanded=False
            ):
                frame_idx = st.slider(
                    "Select frame to plot displacement field:",
                    min_value=0,
                    max_value=len(st.session_state.displacementList) - 1,
                    value=len(st.session_state.displacementList) - 1,
                )
                dis = st.session_state.displacementList[frame_idx]
                if st.session_state.dims["xyt"]:
                    fig = plot_dis_vec(dis * mue2pix, mode=mode)
                    st.pyplot(fig)
                if st.session_state.dims["xyzct"]:
                    fig = plt.figure()
                    if mode == "field":
                        plt.quiver(dis[:, :, 2] * mue2pix, dis[:, :, 1] * mue2pix)
                    elif mode == "magnitude":
                        plt.imshow(
                            np.sqrt(sum([dis[:, :, i] ** 2 for i in range(3)]))
                            * mue2pix,
                            cmap="jet",
                            origin="lower",
                        )
                        plt.colorbar()
                    elif mode == "both":
                        plt.imshow(
                            np.sqrt(sum([dis[:, :, i] ** 2 for i in range(3)]))
                            * mue2pix,
                            cmap="jet",
                            origin="lower",
                        )
                        plt.quiver(dis[:, :, 2] * mue2pix, dis[:, :, 1] * mue2pix)
                    st.pyplot(fig)
        elif len(st.session_state.displacementList) == 1:
            dis = st.session_state.displacementList[-1]
            fig = plot_dis_vec(dis * mue2pix, mode=mode)
            st.pyplot(fig)

    # Traction Force reconstruction
    if st.button("Run Traction Force on All Frames", type="primary"):
        if len(st.session_state.displacementList) == 0:
            st.error("Please run DFT on all frames first.")
        else:
            with st.spinner("Computing traction forces for all frames..."):
                traction_list = []
                progress_bar = st.progress(0)
                for i, dis in enumerate(st.session_state.displacementList):
                    # Scale displacement by micrometer-to-pixel ratio
                    dis_scaled = dis * mue2pix

                    # Compute traction for this frame
                    if st.session_state.opticalflow:
                        traction = tract(
                            dis_scaled,
                            E,
                            nu,
                            mue2pix,
                            alpha0,
                            h,
                            z,
                            d,  # regularization enabled
                        )
                    else:
                        traction = tract(
                            dis_scaled,
                            E,
                            nu,
                            mue2pix,
                            alpha0,
                            h,
                            z,
                            d,
                            [True, step_size],  # regularization enabled
                        )
                    traction_list.append(traction)
                    progress_bar.progress(
                        (i + 1) / len(st.session_state.displacementList)
                    )

                # Store all traction results
                st.session_state.tractionList = traction_list
                st.success(
                    f"✅ Traction forces computed for all {len(traction_list)} frames."
                )

    with st.spinner("Plotting Tractions..."):
        if len(st.session_state.tractionList) > 0:
            if len(st.session_state.tractionList) > 1:
                with st.expander(
                    "🔍 View Traction Field (Select Frame)", expanded=False
                ):
                    frame_idx = st.slider(
                        "Select frame to plot stress field:",
                        min_value=0,
                        max_value=len(st.session_state.tractionList) - 1,
                        value=len(st.session_state.tractionList) - 1,
                    )

                    traction = st.session_state.tractionList[frame_idx]
                    if traction is not None:
                        fig = plot_dis_vec(traction["tractions"].real, mode=mode)
                        st.pyplot(fig)
                    else:
                        st.warning("Traction computation failed for this frame.")
            elif len(st.session_state.tractionList) == 1:
                tr = st.session_state.tractionList[-1]["tractions"].real
                fig = plot_dis_vec(tr, mode=mode)
                st.pyplot(fig)

    # Overlay with microscope image
    if (
        st.session_state.current_frame is not None
        and st.session_state.tractionList
        and not st.session_state.opticalflow
    ):
        with st.expander("🔬+🦠 Overlay traction field and Micropscopy image"):
            fig = plt.figure()
            if st.session_state.roi_shape is not None:
                y0 = st.session_state.roi_shape["y0"]
                x0 = st.session_state.roi_shape["x0"]
                w = st.session_state.roi_shape["w"]
                h = st.session_state.roi_shape["h"]
                if st.session_state.before_img is not None:
                    st.write(st.session_state.before_img.shape)
                frame_idx = st.slider(
                    "Choose a frame",
                    min_value=0,
                    max_value=len(st.session_state.tractionList) - 1,
                    value=0,
                )

                if (
                    st.session_state.dims["xyzct"]
                    and st.session_state.check_crop
                    and st.session_state.before_all is not None
                ):
                    frame_idx_z = st.slider(
                        "Choose a slice",
                        min_value=0,
                        max_value=len(st.session_state.before_all[0]) - 1,
                        value=0,
                    )
                    frame_idx_channel = st.slider(
                        "Choose a channel",
                        min_value=0,
                        max_value=len(st.session_state.before_all[0][0]) - 1,
                        value=0,
                    )
                    img = st.session_state.before_all[frame_idx][frame_idx_z][
                        frame_idx_channel
                    ][y0 : y0 + h, x0 : x0 + w]
                    fy = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 1
                    ].real
                    fx = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 2
                    ].real
                    x = np.arange(0, img.shape[1], step_size)
                    y = np.arange(0, img.shape[0], step_size)
            if st.session_state.before_all is not None:
                if st.session_state.dims["xyzct"] and not st.session_state.check_crop:
                    frame_idx = st.slider(
                        "Choose a frame",
                        min_value=0,
                        max_value=len(st.session_state.tractionList) - 1,
                        value=0,
                    )
                    frame_idx_z = st.slider(
                        "Choose a slice",
                        min_value=0,
                        max_value=len(st.session_state.before_all[0]) - 1,
                        value=0,
                    )
                    frame_idx_channel = st.slider(
                        "Choose a channel",
                        min_value=0,
                        max_value=len(st.session_state.before_all[0][0]) - 1,
                        value=0,
                    )
                    img = st.session_state.before_all[frame_idx][frame_idx_z][
                        frame_idx_channel
                    ]
                    fy = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 1
                    ].real
                    fx = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 2
                    ].real
                    x = np.arange(0, img.shape[1], step_size)
                    y = np.arange(0, img.shape[0], step_size)

                if (
                    st.session_state.dims["xyt"]
                    and st.session_state.check_crop
                    and st.session_state.roi_shape is not None
                ):
                    frame_idx = st.slider(
                        "Choose a frame",
                        min_value=0,
                        max_value=len(st.session_state.tractionList) - 1,
                        value=0,
                        key="xyt",
                    )
                    y0 = st.session_state.roi_shape["y0"]
                    x0 = st.session_state.roi_shape["x0"]
                    w = st.session_state.roi_shape["w"]
                    h = st.session_state.roi_shape["h"]
                    img = st.session_state.before_all[frame_idx][
                        y0 : y0 + h, x0 : x0 + w
                    ]
                    fy = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 0
                    ].real
                    fx = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 1
                    ].real
                    if st.session_state.ElastixCheck:
                        x = np.arange(0, img.shape[1], step_size)
                        y = np.arange(0, img.shape[0], step_size)
                    else:
                        x = np.arange(step_size, img.shape[1] - step_size, step_size)
                        y = np.arange(step_size, img.shape[0] - step_size, step_size)
                if st.session_state.dims["xyt"] and not st.session_state.check_crop:
                    frame_idx = st.slider(
                        "Choose a frame",
                        min_value=0,
                        max_value=len(st.session_state.tractionList) - 1,
                        value=0,
                        key="xytcrop",
                    )
                    img = st.session_state.before_all[frame_idx]
                    fy = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 0
                    ].real
                    fx = st.session_state.tractionList[frame_idx]["tractions"][
                        :, :, 1
                    ].real
                    if st.session_state.ElastixCheck:
                        x = np.arange(0, img.shape[1], step_size)
                        y = np.arange(0, img.shape[0], step_size)
                    else:
                        x = np.arange(step_size, img.shape[1] - step_size, step_size)
                        y = np.arange(step_size, img.shape[0] - step_size, step_size)

                plt.imshow(img, origin="lower")
                # Create meshgrid
                X, Y = np.meshgrid(x, y)
                plt.quiver(X, Y, fx, fy)
                st.pyplot(fig)
                # st.write(h,w)

    if st.button("🗑️ Clear All Data (Manual Reset)"):
        st.session_state.clear()
        st.rerun()

    if (
        hasattr(st.session_state, "displacementList")
        and st.session_state.displacementList
    ):
        if hasattr(st.session_state, "tractionList") and st.session_state.tractionList:
            # Combine both
            with st.expander(
                "💾 Download All Results (Displacement + Traction)", expanded=False
            ):
                # Create a dictionary to save
                data_to_save = {
                    "displacement_fields": st.session_state.displacementList,
                    "traction_fields": st.session_state.tractionList,
                    "metadata": {
                        "mue2pix": mue2pix,
                        "E": E,
                        "nu": nu,
                        "h": h,
                        "z": z,
                        "d": d,
                        "half_window_size": half_window_size,
                        "step_size": step_size,
                        "mode": mode,
                    },
                }

                # Save to in-memory buffer
                import io

                buf = io.BytesIO()
                np.savez_compressed(buf, **data_to_save)
                buf.seek(0)

                st.download_button(
                    label="💾 Download All Results (NPZ)",
                    data=buf,
                    file_name="tfm_results.npz",
                    mime="application/octet-stream",
                )
        else:
            # Only displacement available
            with st.expander("💾 Download Displacement Fields", expanded=False):
                data_to_save = {
                    "displacement_fields": st.session_state.displacementList,
                    "metadata": {
                        "mue2pix": mue2pix,
                        "half_window_size": half_window_size,
                        "step_size": step_size,
                        "mode": mode,
                    },
                }

                buf = io.BytesIO()
                np.savez_compressed(buf, **data_to_save)
                buf.seek(0)

                st.download_button(
                    label="💾 Download Displacement Fields (NPZ)",
                    data=buf,
                    file_name="displacement_fields.npz",
                    mime="application/octet-stream",
                )

    # --- Optional: Download Traction Only ---
    if hasattr(st.session_state, "tractionList") and st.session_state.tractionList:
        with st.expander("💾 Download Traction Fields", expanded=False):
            data_to_save = {
                "traction_fields": st.session_state.tractionList,
                "metadata": {
                    "E": E,
                    "nu": nu,
                    "h": h,
                    "z": z,
                    "d": d,
                    "alpha0": alpha0,
                    "mue2pix": mue2pix,
                    "half_window_size": half_window_size,
                    "step_size": step_size,
                    "mode": mode,
                },
            }

            buf = io.BytesIO()
            np.savez_compressed(buf, **data_to_save)
            buf.seek(0)

            st.download_button(
                label="💾 Download Traction Fields (NPZ)",
                data=buf,
                file_name="traction_fields.npz",
                mime="application/octet-stream",
            )

    with st.expander("❓ Help & Documentation"):
        st.markdown("""
        - **Before Image**: Timelapse (TIFF) of cell moving
        - **After Image**: Reference (static) image
        - **Half Window Size**: Smaller = more detail, larger = more robust
        - **Step Size**: Smaller = higher resolution, slower
        - **Traction Force**: Computed using FFTC (sort of).
        """)
        st.markdown("### 🔗 Access the Executor")
        st.image(
            "Web-Interface-Python-Traction-Force-Microsopy-qr-code.elabftw.png",
            caption="QR Code for Access to Executor",
        )
        st.markdown(
            "[👉 Click here to access the executor Documentation (opens in new tab)](https://executor.physik3.uni-goettingen.de:1443/database.php?mode=view&id=401)",
            unsafe_allow_html=True,
        )
        st.markdown("### 📜 Relevant papers")
        st.markdown(
            "[👉 Traction fields, moments, and strain energy that cells exert on their surroundings (opens in new tab)](https://journals.physiology.org/doi/full/10.1152/ajpcell.00270.2001)",
            unsafe_allow_html=True,
        )
        st.markdown(
            "[Traction force microscopy with optimized regularization and automated Bayesian parameter selection for comparing cells (opens in new tab)](https://doi.org/10.1038/s41598-018-36896-x)"
        )
        st.markdown(
            "[Spatio-temporal analysis of eukaryotic cell motility by improved force cytometry (opens in new tab)](https://www.pnas.org/doi/pdf/10.1073/pnas.0705815104)"
        )
        st.markdown(
            "[Imaging in-plane and normal stresses near an interface crack using traction force microscopy (opens in new tab)](https://www.pnas.org/doi/pdf/10.1073/pnas.1005537107)"
        )
        st.markdown(
            "[Analysis of monocyte cell tractions in 2.5D reveals mesoscale mechanics of podosomes during substrate-indenting cell protrusion. (opens in new tab)](https://journals.biologists.com/jcs/article-pdf/135/10/jcs259042/3581113/jcs259042.pdf)"
        )
