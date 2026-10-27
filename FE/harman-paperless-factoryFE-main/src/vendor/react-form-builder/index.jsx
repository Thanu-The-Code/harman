/**
  * <ReactFormBuilder />
*/

import React from 'react';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { IntlProvider } from 'react-intl';
import Preview from './preview';
import Toolbar from './toolbar';
import FormGenerator from './form';
import store from './stores/store';
import Registry from './stores/registry';
import AppLocale from './language-provider';
import {
  createOcrClient, OcrDocumentView, OcrTemplateImport, loadIntoBuilder, OcrScanFill, OcrDigitize, OcrExport,
} from './ocr';

class ReactFormBuilder extends React.Component {
  constructor(props) {
    super(props);

    this.state = {
      editMode: false,
      editElement: null,
    };
    this.editModeOn = this.editModeOn.bind(this);
  }

  editModeOn(data, e) {
    e.preventDefault();
    e.stopPropagation();
    if (this.state.editMode) {
      this.setState({ editMode: !this.state.editMode, editElement: null });
    } else {
      this.setState({ editMode: !this.state.editMode, editElement: data });
    }
  }

  manualEditModeOff() {
    if (this.state.editMode) {
      this.setState({
        editMode: false,
        editElement: null,
      });
    }
  }

  render() {
    const toolbarProps = {
      showDescription: this.props.show_description,
    };

    const language = this.props.locale ? this.props.locale : 'en';
    const currentAppLocale = AppLocale[language];
    if (this.props.toolbarItems) { toolbarProps.items = this.props.toolbarItems; }
    return (
      <DndProvider backend={HTML5Backend} context={window}>
        <IntlProvider
          locale={currentAppLocale.locale}
          messages={currentAppLocale.messages}>
          <div>
            {/* <div>
           <p>
             It is easy to implement a sortable interface with React DnD. Just make
             the same component both a drag source and a drop target, and reorder
             the data in the <code>hover</code> handler.
           </p>
           <Container />
         </div> */}
            <div className="react-form-builder clearfix">
              <div>
                <Preview
                  files={this.props.files}
                  manualEditModeOff={this.manualEditModeOff.bind(this)}
                  showCorrectColumn={this.props.showCorrectColumn}
                  parent={this}
                  data={this.props.data}
                  url={this.props.url}
                  saveUrl={this.props.saveUrl}
                  onLoad={this.props.onLoad}
                  onPost={this.props.onPost}
                  editModeOn={this.editModeOn}
                  editMode={this.state.editMode}
                  variables={this.props.variables}
                  registry={Registry}
                  editElement={this.state.editElement}
                  renderEditForm={this.props.renderEditForm}
                  saveAlways={this.props.saveAlways}
                />
                <Toolbar {...toolbarProps} customItems={this.props.customToolbarItems} />
              </div>
            </div>
          </div>
        </IntlProvider>
      </DndProvider>
    );
  }
}

/**
 * The builder's parts, for a host page that lays them out itself (the designer puts the
 * canvas in the middle and the palette in a side panel): wrap both in <BuilderProvider>,
 * render <Preview> as the canvas and <Toolbar layout="tiles"> as the palette.
 */
function BuilderProvider({ locale, children }) {
  const currentAppLocale = AppLocale[locale || 'en'];
  return (
    <DndProvider backend={HTML5Backend} context={window}>
      <IntlProvider locale={currentAppLocale.locale} messages={currentAppLocale.messages}>
        {children}
      </IntlProvider>
    </DndProvider>
  );
}

function ReactFormGenerator(props) {
  const language = props.locale ? props.locale : 'en';
  const currentAppLocale = AppLocale[language];
  return (
    <IntlProvider
      locale={currentAppLocale.locale}
      messages={currentAppLocale.messages}>
      <FormGenerator {...props} />
    </IntlProvider>
  );
}

const FormBuilders = {};
FormBuilders.ReactFormBuilder = ReactFormBuilder;
FormBuilders.ReactFormGenerator = ReactFormGenerator;
FormBuilders.ElementStore = store;
FormBuilders.BuilderProvider = BuilderProvider;
FormBuilders.Preview = Preview;
FormBuilders.Toolbar = Toolbar;
FormBuilders.Registry = Registry;
FormBuilders.Ocr = {
  createOcrClient, OcrDocumentView, OcrTemplateImport, loadIntoBuilder, OcrScanFill, OcrDigitize, OcrExport,
};

export default FormBuilders;

export {
  ReactFormBuilder, ReactFormGenerator, store as ElementStore, Registry, BuilderProvider, Preview, Toolbar,
  createOcrClient, OcrDocumentView, OcrTemplateImport, loadIntoBuilder, OcrScanFill, OcrDigitize, OcrExport,
};
