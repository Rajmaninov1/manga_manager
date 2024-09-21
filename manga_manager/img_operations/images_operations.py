import io
import logging
import os

import cv2
import numpy as np
from PIL import Image, ImageStat
from PIL.ImageFile import ImageFile

from manga_manager.manga_processor.env_vars import final_document_width, final_document_height

logger = logging.getLogger('_manga_manager_')


def average_brightness(image: Image.Image) -> float:
    """
    Calculates the average brightness of an image.
    """
    grayscale_image = image.convert('L')  # Convert the image to grayscale
    stat = ImageStat.Stat(grayscale_image)
    return stat.mean[0]  # Return the average brightness


def best_background_for_image(image: Image.Image) -> tuple[int, int, int]:
    """
    Determines whether an image looks better on a black or white background based on average brightness.

    Returns:
    - (0, 0, 0) for black background.
    - (255, 255, 255) for white background.
    """
    avg_brightness = average_brightness(image)

    # Calculate contrast with white and black backgrounds
    contrast_with_white = abs(255 - avg_brightness)  # White background contrast
    contrast_with_black = avg_brightness  # Black background contrast

    # Choose the background that provides better contrast
    if contrast_with_white > contrast_with_black:
        return 0, 0, 0  # Image looks better on a black background
    else:
        return 255, 255, 255  # Image looks better on a white background



def denoise_and_sharpen_image(image: ImageFile, denoise_strength=10, sharpen_strength=2) -> Image:
    """
    Denoises and sharpens an image after cropping.

    Parameters:
    - image: The cropped image as a PIL Image.
    - denoise_strength: Strength for denoising the image.
    - sharpen_strength: Strength for sharpening the image.
    """
    try:
        # Convert PIL Image to OpenCV format
        image_cv = cv2.cvtColor(np.array(image, dtype=np.uint8), cv2.COLOR_RGB2BGR)

        # Apply denoising using Non-Local Means Denoising (or Bilateral Filter)
        image_denoised = cv2.fastNlMeansDenoisingColored(image_cv, None, denoise_strength, denoise_strength, 7, 21)

        # Sharpen the image using a kernel
        sharpening_kernel = np.array([[-1, -1, -1],
                                      [-1, 9 + sharpen_strength, -1],
                                      [-1, -1, -1]])
        image_sharpened = cv2.filter2D(image_denoised, -1, sharpening_kernel)

        # Convert back to PIL Image
        image_sharpened_pil = Image.fromarray(cv2.cvtColor(image_sharpened, cv2.COLOR_BGR2RGB))

        logger.info('Image denoised and sharpened.')
        return image_sharpened_pil
    except Exception as e:
        logger.error(f'Error in denoise_and_sharpen_image: {e}', exc_info=True)
        return image


def is_not_manga(image: ImageFile) -> bool:
    """
    Detect if an image is likely from a manga or a web-comic/manhwa based on its aspect ratio and color content.
    """
    try:
        width, height = image.size
        aspect_ratio = width / height
        img_np = np.array(image, dtype=np.uint8)

        is_colored = True

        if len(img_np.shape) == 2:
            is_colored = False
        elif len(img_np.shape) == 3:
            if np.all(img_np[:, :, 0] == img_np[:, :, 1]) and np.all(img_np[:, :, 1] == img_np[:, :, 2]):
                is_colored = False

        if aspect_ratio > 1.5 and is_colored:
            logger.info("Image classified as manga.")
            return True
        elif not is_colored:
            logger.info("Image classified as non-manga (grayscale).")
            return False
        else:
            logger.info("Image classified as manga (non-grayscale).")
            return True
    except Exception as e:
        logger.error(f"Error in is_not_manga: {e}", exc_info=True)
        return False


def detect_blank_or_dark_spaces(image, threshold_light=240, threshold_dark=15):
    """
    Detects horizontal blank or dark spaces in an image by checking each row of pixels.
    """
    try:
        spaces = []
        width, height = image.size
        grayscale_img = image.convert("L")

        for y in range(height):
            row = grayscale_img.crop((0, y, width, y + 1))
            if all(pixel > threshold_light for pixel in row.getdata()) or all(
                    pixel < threshold_dark for pixel in row.getdata()):
                spaces.append(y)

        logger.info(f"Detected {len(spaces)} blank or dark spaces.")
        return spaces
    except Exception as e:
        logger.error(f"Error in detect_blank_or_dark_spaces: {e}", exc_info=True)
        return []


def crop_image_by_blank_or_dark_space(image, blank_threshold=240, dark_threshold=30) -> ImageFile:
    """
    Crops the image by detecting regions of blank (white) or dark (black) space.
    """
    try:
        grayscale_image = image.convert('L')
        np_image = np.array(grayscale_image, dtype=np.uint8)

        blank_mask = np_image > blank_threshold
        dark_mask = np_image < dark_threshold
        crop_mask = ~(blank_mask | dark_mask)

        coords = np.argwhere(crop_mask)
        if coords.size > 0:
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0) + 1
            cropped_image = image.crop((x0, y0, x1, y1))
            logger.info("Image cropped by blank or dark spaces.")
        else:
            logger.warning("No valid cropping region found, returning original image.")
            cropped_image = image
        return cropped_image
    except Exception as e:
        logger.error(f"Error in crop_image_by_blank_or_dark_space: {e}", exc_info=True)
        return image


def enhance_image_for_screen(img, screen_width=final_document_width, screen_height=final_document_height) -> Image:
    """
    Enhances an image to fit a screen with given resolution pixels while maintaining the aspect ratio.
    """
    try:
        img_width, img_height = img.size
        img_aspect_ratio = img_width / img_height
        screen_aspect_ratio = screen_width / screen_height

        if img_aspect_ratio > screen_aspect_ratio:
            new_width = screen_width
            new_height = int(screen_width / img_aspect_ratio)
        else:
            new_height = screen_height
            new_width = int(screen_height * img_aspect_ratio)

        resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        new_img = Image.new(
            mode="RGB", size=(screen_width, screen_height), color=best_background_for_image(resized_img)
        )
        paste_x = (screen_width - new_width) // 2
        paste_y = (screen_height - new_height) // 2

        new_img.paste(resized_img, (paste_x, paste_y))
        logger.info("Image enhanced for screen.")
        return new_img
    except Exception as e:
        logger.error(f"Error in enhance_image_for_screen: {e}", exc_info=True)
        return img


def split_image_by_blank_or_dark_spaces(
        image,
        threshold_light=240,
        threshold_dark=15,
        min_gap=20,
        min_segment_height=75
) -> list[ImageFile]:
    """
    Splits an image into segments wherever horizontal blank spaces are found,
    avoiding tiny segments smaller than min_segment_height.
    """
    try:
        blank_spaces = detect_blank_or_dark_spaces(image, threshold_light, threshold_dark)
        split_positions = [0] + blank_spaces + [image.height]

        cropped_images = []

        for i in range(1, len(split_positions)):
            if split_positions[i] - split_positions[i - 1] > min_gap:
                segment = image.crop((0, split_positions[i - 1], image.width, split_positions[i]))

                # Check the height of the segment before processing
                if segment.height >= min_segment_height:
                    segment_cropped = crop_image_by_blank_or_dark_space(segment)
                    segment_enhanced = enhance_image_for_screen(segment_cropped)
                    cropped_images.append(segment_enhanced)
                else:
                    logger.warning(
                        f"Skipped segment due to small height: {segment.height} (min required: {min_segment_height})")

        logger.info(f"Split image into {len(cropped_images)} segments.")
        return cropped_images
    except Exception as e:
        logger.error(f"Error in split_image_by_blank_or_dark_spaces: {e}", exc_info=True)
        return []


def split_and_crop_image(image: ImageFile, page_num: int, img_index: int) -> list[ImageFile]:
    images: list[ImageFile] = []
    try:
        logger.info(f"Processing image from page {page_num + 1}, index {img_index + 1}.")
        if page_num != 0 and is_not_manga(image):
            for image_segment in split_image_by_blank_or_dark_spaces(image=image):
                # Apply denoising and sharpening after cropping
                # denoised_sharpened_image = denoise_and_sharpen_image(image_segment)
                images.append(image_segment)
        else:
            image_cropped = enhance_image_for_screen(crop_image_by_blank_or_dark_space(image))
            # Apply denoising and sharpening after cropping
            # denoised_sharpened_image = denoise_and_sharpen_image(image_cropped)
            images.append(image_cropped)
    except Exception as e:
        logger.error(f"Error processing image on page {page_num + 1}: {e}", exc_info=True)
    return images


def delete_images_in_folder(folder_path, extensions=("png", "jpg", "jpeg", "bmp", "gif")) -> None:
    """
    Delete all image files in a folder. Images are detected by their file extensions.
    """
    try:
        files = os.listdir(folder_path)

        for file in files:
            file_path = os.path.join(folder_path, file)

            if file.lower().endswith(extensions) and os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"Deleted image: {file}")
    except Exception as e:
        logger.error(f"Error deleting images in folder {folder_path}: {e}", exc_info=True)


def temporal_pdf_image(image_path: str, width: int, height: int) -> str:
    with Image.open(image_path) as img:
        image_path = image_path.split('.')[0]
        img = img.convert('RGB')  # Ensure it's in RGB format

        # Resize the image to fit A4 size while maintaining aspect ratio
        img_width, img_height = img.size
        aspect = img_width / img_height

        if aspect > 1:  # Wide image
            new_width = width
            new_height = width / aspect
        else:  # Tall image
            new_height = height
            new_width = height * aspect

        img = img.resize((int(new_width), int(new_height)), Image.Resampling.LANCZOS)

        # Save the image to a temporary file and draw on canvas
        temp_img_path = f"{image_path}.pdf"
        img.save(temp_img_path, "PDF", quality=85)

        return temp_img_path


def image_generator(
        *,
        image_files_paths: list[str],
        image_folder_path: str
):
    """Lazy loads and yields images one at a time."""
    for image_file_path in image_files_paths:
        logger.info(f"Processing image file: {image_file_path}")
        with load_image_by_path(image_folder_path=image_folder_path, image_file_path=image_file_path) as image:
            image = image.convert('RGB')
            yield image.copy()
            image.close()


def load_images_list_by_path(
        *,
        image_files_paths: list[str],
        image_folder_path: str
) -> list[Image]:
    """
    Load images from a list of paths.
    """
    images = []
    try:
        for image_path in image_files_paths:
            full_path = os.path.join(image_folder_path, image_path)
            images.append(Image.open(full_path).convert('RGB'))
            logger.info(f"Loaded image: {image_path}")
    except Exception as e:
        logger.error(f"Error loading images from path {image_folder_path}: {e}", exc_info=True)
    return images


def load_image_by_path(
        *,
        image_file_path: str,
        image_folder_path: str
) -> Image:
    """
    Load a single image by its path.
    """
    try:
        full_path = os.path.join(image_folder_path, image_file_path)
        image = Image.open(full_path).convert('RGB')
        logger.info(f"Loaded image: {image_file_path}")
        return image
    except Exception as e:
        logger.error(f"Error loading image {image_file_path}: {e}", exc_info=True)
        return None


def load_image_by_str_data(image_data) -> ImageFile | None:
    """
    Load an image from byte data.
    """
    try:
        image = Image.open(io.BytesIO(image_data))
        logger.info("Loaded image from byte data.")
        return image
    except Exception as e:
        logger.error(f"Error loading image from byte data: {e}", exc_info=True)
        return None


def save_image_to_path(image: ImageFile, path_to_save: str, quality=75):
    """
    Save an image to a specified path with a given quality.
    """
    try:
        image.save(path_to_save, format='JPEG', quality=quality)
        logger.info(f"Saved image to {path_to_save}.")
    except Exception as e:
        logger.error(f"Error saving image to {path_to_save}: {e}", exc_info=True)
