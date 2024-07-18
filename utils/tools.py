def allowed_file(filename):
    file_allow = [".docx",".html",".pdf",".txt"]
    for file_ in file_allow:
        if file_ in filename:
            return True
        
    return False

