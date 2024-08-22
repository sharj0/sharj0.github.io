def _add_widget_for_value(self, key, value, layout):
    ellipsis_font = QFont()
    ellipsis_font.setPointSize(14)
    ellipsis_font.setBold(True)

    # get base key
    base_key = key
    for suffix in suffixes:
        if key.endswith(suffix):
            base_key = key[:-len(suffix)]
            break

    field_font = QFont()
    field_font.setPointSize(self.field_font_size)

    tooltip = self.tooltips.get(base_key)

    if "_COMMENT" in key:
        # Display comments as QLabel
        comment_layout = QHBoxLayout()
        spacer_label = QLabel()  # This label will simulate the tabbing
        spacer_label.setFixedWidth(self.spacer)  # Adjust this value for your desired amount of spacing
        comment_label = QLabel(value)
        comment_font = QFont()
        comment_font.setPointSize(self.comment_font_size)
        comment_label.setFont(comment_font)
        if tooltip:
            comment_label.setToolTip(tooltip)
        # Make the comment appear in grey
        comment_label.setStyleSheet("color: grey;")
        comment_layout.addWidget(spacer_label)
        comment_layout.addWidget(comment_label)
        layout.addLayout(comment_layout)
    elif "_SELECT_LAYER" in key:
        h_layout = QHBoxLayout()
        combobox = NoScrollQComboBox()
        combobox.addItem("previous input")
        index = combobox.findText("previous input")
        italic_font = QFont()
        italic_font.setItalic(True)
        combobox.setItemData(index, italic_font, Qt.FontRole)
        combobox.setItemData(index, QColor("grey"), Qt.ForegroundRole)
        for layer_name in self.get_available_qgis_layers():
            combobox.addItem(layer_name)
        combobox.currentTextChanged.connect(lambda text, k=key: self.update_textfield_from_dropdown(k, text))

        if tooltip:
            combobox.setToolTip(tooltip)
        h_layout.addWidget(combobox, 1)
        # Adding a "..." button after the dropdown
        ellipsis_button = QPushButton("...")
        ellipsis_button.setFont(ellipsis_font)
        ellipsis_button.clicked.connect(lambda text, k=key: self.update_textfield_from_layer_file_dialog(k))
        if tooltip:
            ellipsis_button.setToolTip(tooltip)
        h_layout.addWidget(ellipsis_button)
        layout.addLayout(h_layout)
    elif "_SELECT_FILE" in key:
        h_layout = QHBoxLayout()
        folder_button = QPushButton("...")
        folder_button.setFont(ellipsis_font)
        folder_button.clicked.connect(lambda text, k=key: self.update_textfield_from_file_dialog(k))

        if tooltip:
            folder_button.setToolTip(tooltip)
        h_layout.addWidget(folder_button)
        layout.addLayout(h_layout)
    elif "_SELECT_FOLDER" in key:
        h_layout = QHBoxLayout()
        folder_button = QPushButton("...")
        folder_button.setFont(ellipsis_font)
        folder_button.clicked.connect(lambda text, k=key: self.update_textfield_from_folder_dialog(k))
        if tooltip:
            folder_button.setToolTip(tooltip)
        h_layout.addWidget(folder_button)
        layout.addLayout(h_layout)
    elif "_VIDEO" in key:
        # Add a button to play the video next to the existing QLineEdit
        base_key = key.replace("_VIDEO", "")
        line_edit = self.findChild(plugin_tools.Drag_and_Drop, base_key)
        if not line_edit:
            checkbox = self.findChild(QCheckBox, base_key)
            if checkbox:
                h_layout = self.findChild(QHBoxLayout, f"layout_{base_key}")
                if not h_layout:
                    h_layout = QHBoxLayout()
                    h_layout.setObjectName(f"layout_{base_key}")
                    field_font = QFont()
                    field_font.setPointSize(self.field_font_size)
                    checkbox.setFont(field_font)
                    h_layout.addWidget(checkbox)
                    layout.addLayout(h_layout)
            else:
                line_edit = QLineEdit(str(value))
                line_edit.setFont(field_font)
                line_edit.setObjectName(base_key)  # Set the object name for later lookup
                line_edit_label = QLabel(base_key)
                line_edit_label.setFont(field_font)
                if tooltip:
                    line_edit.setToolTip(tooltip)
                    line_edit_label.setToolTip(tooltip)
                h_layout = QHBoxLayout()
                h_layout.setObjectName(f"layout_{base_key}")
                h_layout.addWidget(line_edit_label)
                h_layout.addWidget(line_edit)
                layout.addLayout(h_layout)
        else:
            h_layout = self.findChild(QHBoxLayout, f"layout_{base_key}")
        vid_button = QPushButton()
        vid_icon_path = os.path.join(plugin_dir, "vid_icon.png")
        vid_button.setIcon(QIcon(vid_icon_path))
        vid_button.setIconSize(QSize(24, 24))
        vid_button.setFixedSize(QSize(24, 24))  # Set fixed size to make it square
        vid_button.clicked.connect(lambda: self.play_vid(os.path.join(self.video_folder_path, value)))
        h_layout.addWidget(vid_button)
    else:
        if isinstance(value, bool):
            # Use QCheckBox for boolean values
            checkbox = QCheckBox(key)
            checkbox.setFont(field_font)
            checkbox.setChecked(value)
            checkbox.setObjectName(key)
            if tooltip:
                checkbox.setToolTip(tooltip)
            h_layout = QHBoxLayout()
            h_layout.setObjectName(f"layout_{key}")
            h_layout.addWidget(checkbox)
            layout.addLayout(h_layout)
            if key + "_VIDEO" in self.data:
                vid_button = QPushButton()
                vid_icon_path = os.path.join(plugin_dir, "vid_icon.png")
                vid_button.setIcon(QIcon(vid_icon_path))
                vid_button.setIconSize(QSize(24, 24))
                vid_button.setFixedSize(QSize(24, 24))  # Set fixed size to make it square
                vid_button.clicked.connect(
                    lambda: self.play_vid(os.path.join(self.video_folder_path, self.data[key + "_VIDEO"])))
                h_layout.addWidget(vid_button)
        else:
            # Use QLineEdit for other types
            line_edit = plugin_tools.Drag_and_Drop(str(value))

            # Override the base QLineEdit class with the mousePressEvent and sets it select all, ensuring when the lineEdit is clicked once, it should highlight all text in the box by default
            line_edit.mousePressEvent = lambda _: line_edit.selectAll()

            line_edit.setFont(field_font)
            line_edit.setAcceptDrops(True)
            line_edit.setObjectName(key)  # Set the object name for later lookup
            line_edit_label = QLabel(key)
            line_edit_label.setFont(field_font)
            if tooltip:
                line_edit.setToolTip(tooltip)
                line_edit_label.setToolTip(tooltip)
            h_layout = QHBoxLayout()
            h_layout.setObjectName(f"layout_{key}")
            h_layout.addWidget(line_edit_label)
            h_layout.addWidget(line_edit)
            layout.addLayout(h_layout)