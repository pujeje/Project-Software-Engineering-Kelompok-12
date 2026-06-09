from PIL import Image
import pytesseract

# kalau di Windows, pastikan path ke tesseract.exe sesuai lokasi instalasi kamu
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ganti 'struk.png' dengan nama file struk kamu
img = Image.open("struk.png")
text = pytesseract.image_to_string(img)

print("Hasil OCR:")
print(text)
