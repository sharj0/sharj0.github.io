
# from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph

from PyPDF2 import PdfReader, PdfWriter


# This module is lets the user create a pdf file of the settings_dict so that everytime it gets run, there is a settings_json file that is created in the desired path for Peter tto go through and say AHA it was YOU sir who indeed made a mistake not ME.
# The input is the file path with the pdf name (if you want to create iterative versions, it should be done outside this python library). This function also requires the settings dictionary input and can account for any amount of settings, but spacing on the page is not accounted for yet (the pixel and inch math is weird).
def create_settings_json_pdf_page(settings_pdf_output_path, settings_dict):

    # One inch is 72 points in the reportlab library, so the new page for settings is 10 inches, this is not necessary but I kept it
    page_height = 10 * 72
    page_width = 20 * 72

    #This creates a blank document with the above page size (you can import standardized pages (like A4 and letter through reportlab or make your own custom one)
    doc = SimpleDocTemplate(settings_pdf_output_path, pagesize=(page_width, page_height))

    #Creates a style for the text (times new roman, line spacing etc.)
    style = ParagraphStyle(
        name="CustomStyle",
        fontName="Times-Roman",
        fontSize=12,
        leading=14,  # Line spacing
        leftIndent=0,  # No left margin
        rightIndent=0,  # No right margin
        spaceBefore=0,  # No space before paragraph
        spaceAfter=5,  # Space after paragraph
        alignment=0,  # Left-align the text
    )

    #An empty list to store each key and value in settings_dict
    elements = []

    #Iterates through every key and value in settings_dict
    for key, value in settings_dict.items():

        #Creates a string with the setting identifier/key and the value when user pressed accept
        setting = f"{key}: {value}"

        #Creates a paragraph for each setting and appends into the elements list
        paragraph = Paragraph(setting, style)
        elements.append(paragraph)

    #Creates the document at the output location with the settings
    doc.build(elements)

    # paragraph = Paragraph(setting_1, style)
    #
    # doc.build([paragraph])

    # c = canvas.Canvas(settings_pdf_output_file, pagesize=(10 * 72, 10 * 72))
    # c.setFont("Times-Roman", 12)
    # text_object = c.beginText(30, page_height - 30)
    # max_width = page_width - 30
    #
    #
    #
    # text_object.textLines(c._multiLineText(setting_1, max_width))
    #
    # c.drawText(text_object)
    #
    # c.save()


#This function is just for mag clipper where it appends the settings_dict into the pdf that is already published in the plugin
def append_pdf_page(pdf_path_existing,pdf_path_to_append,pdf_path_merged):
    
    reader = PdfReader(pdf_path_existing)

    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    new_reader = PdfReader(pdf_path_to_append)

    for page in new_reader.pages:
        writer.add_page(page)

    with open(pdf_path_merged, "wb") as f:
        writer.write(f)

if __name__ == "__main__":
    print("0")