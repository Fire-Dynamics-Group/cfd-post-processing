
def input_report_vals(doc, values):
    doc.render(values)


if __name__ == '__main__':
    from docxtpl import DocxTemplate
    document_name = "Template CFD Report - Copy.docx"
    document_path = f"{document_name}" # Path(__file__).parent /"CFD Word Template"/document_name
    doc = DocxTemplate(document_path)
    values = {'CLIENT_NAME': 'testing1'}
    input_report_vals(doc, values)
    # doc.save("input_report.docx")