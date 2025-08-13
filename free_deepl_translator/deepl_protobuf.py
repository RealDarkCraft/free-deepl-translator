fieldfix = {
    "SetPropertyOperation":[6, 11]
}
fieldnext = {
    "StartSessionRequest":[None,"BaseDocument",None,"AppInformation",None],
    "ParticipantRequest":["AppendMessage","UpdateAuthenticationTokenMessage"],
    "ParticipantResponse":["ConfirmedMessage","InitializedMessage","PublishedMessage","MetaInfoMessage"], 
    "BaseDocument":["Field"],
    "Field":[None,None,"CreateAnnotationOperation","SetPropertyOperation"],
    "AppendMessage":["FieldEvent","EventVersion"], #FULL
    "FieldEvent":[None,"TextChangeOperation","CreateAnnotationOperation","RemoveAnnotationOperation","SetPropertyOperation","ParticipantId"], #FULL
    "PublishedMessage":["FieldEvent",None],
    "TextChangeOperation":["TextRange",None],
    "ClientErrorInfo":[None,"DetailCode",None]
}
fieldname = {
    "TextChangeOperation":["range","text"],
    "CreateAnnotationOperation":["annotationId","range","textUnitPayLoad","requestWordAlternativesPayload","providedWordAlternativesPayload","selectWordAlternativePayload","translatorGlossaryReplacementPayload","requestTextUnitAlternativesPayload","translatorProvidedTextUnitAlternativesPayload","selectTextUnitAlternativePayload","translatorRequestAutocompletionPayload","translatorProvidedAutocompletionPayload","translatorSelectAutocompletionPayload","translatorProvidedAutomaticTextUnitAlternativesPayload","selectAutomaticTextUnitAlternativePayload","writeDiffUnitPayload","textFormattingPayload","writeProvidedTextUnitAlternativesPayload","writeProvidedAutomaticTextUnitAlternativesPayload","translatorRequestClarifyPayload","translatorProvidedClarifyQuestionPayload","translatorProvidedClarifyHighlightPayload","translatorSelectClarifyAnswerPayload","writeRequestChangeStyleAlternativesAnnotationPayload","writeProvidedChangeStyleAlternativesAnnotationPayload","writeSelectChangeStyleAlternativeAnnotationPayload","translatorClarifyStatusPayload","styleGuideRuleAppliedAnnotationPayload","writeRequestTemplateAdaptationAnnotationPayload","writeProvidedTemplateAdaptationAnnotationPayload","providedWordAlternativeHighlightPayload","writeInlineSuggestionAnnotationPayload","writeInlineSuggestionSpanAnnotationPayload","writeActOnInlineSuggestionAnnotationPayload","writeInlineSuggestionsTextUnitStateAnnotationPayload"],
    "RemoveAnnotationOperation":["annotationId"],
    "SetPropertyOperation":["propertyName","translatorSourceLanguagesValue","translatorTargetLanguagesValue","translatorRequestedSourceLanguageValue","translatorRequestedTargetLanguageValue",None, "translatorFormalityModesValue","translatorFormalityModeValue","translatorGlossarySupportValue","translatorGlossaryListValue",None, "translatorTextDirectionValue","translatorCalculatedSourceLanguageValue","translatorMaximumTextLengthValue","translatorLanguageModelsValue","translatorLanguageModelValue","translatorGlossaryIdValue","translatorCalculatedTargetLanguageValue","translatorUnsupportedSourceLanguageValue","writeLanguagesValue","writeRequestedLanguageValue","writeCalculatedLanguageValue","writeStyleVariantsValue","writeStyleVariantValue","writeGlossaryIdValue","writeGlossaryListValue","writeGlossarySupportValue","writeMaximumTextLengthValue","writeUnsupportedLanguageValue","translatorSourceLanguageDetectionWeightsValue","writeGlossaryLanguagesValue","writeStyleGuideSupportValue","writeStyleGuideIdValue","writeTemplateAdaptationTemplatesValue","translatorStyleGuideSupportValue","translatorStyleGuideIdValue","interfaceLanguageValue","translatorLanguageModelPreferencesValue","translatorFreeTextPromptListValue","writeFreeTextPromptListValue","writeInlineSuggestionsLoadingValue","writeCorrectionsOnlySupportValue","writeCorrectionsOnlyValue","translatorRtfSupportValue"],
    "ClientErrorInfo":["statusCode","detailCode","fallbackDetailCodes"],
    "DetailCode":["value"],
    "StartSessionRequest":["sessionMode","baseDocument","translatorSessionOptions","appInformation","previousSessionId"],
    "StartSessionResponse":["sessionId","participantId","sessionToken","versionRemovedAt"],
    "ParticipantRequest":["appendMessage", "updateAuthenticationTokenMessage"],
    "ParticipantResponse":["confirmedMessage", "initializedMessage","publishedMessage","metaInfoMessage"],
    "ConfirmedMessage":["currentVersion","throttlingDelay"],
    "InitializedMessage":[""],
    "PublishedMessage":["events","currentVersion"],
    "MetaInfoMessage":["idle","translatorTaskMetaInfo"],
    "Idle":["eventVersion"],
    "AppendMessage":["events","baseVersion"],
    "UpdateAuthenticationTokenMessage":["token"],
    "AppInformation":["os","osVersion","appVersion","appBuild","instanceId"],
    "SessionId":["value"],
    "EventVersion":["value"],
    "FieldEvent":["fieldName","textChangeOperation","createAnnotationOperation","removeAnnotationOperation","setPropertyOperation","participantId"],
    "ParticipantId":["value"],
    "BaseDocument":["fields"],
    "Field":["fieldName","text","annotations","properties"],
    "TextRange":["start","end"]
}
def getKeyName(name, key):
    number = int(key)
    return fieldname[name][number-1]
def getKeyValue(name, key):
    return fieldname[name].index(key) + 1
        
        

def ProtobufAddNames(js, name, is_type = False):
    if (type(js) == dict):
        new_json = {}
        d = 0
        for key, value in js.items():
            xname = getKeyName(name, key)
            if (((type(value) == dict and (is_type == False or value["type"] == "message")) or (type(value) == list and len(value) > 0 and type(value[0]) == dict)) and fieldnext.get(name) != None and fieldnext.get(name)[int(key)-1] != None):
                if (is_type == False):
                    new_val = ProtobufAddNames(value, fieldnext.get(name)[int(key)-1], is_type)
                else:
                    new_val = value
                    new_val["message_typedef"] = ProtobufAddNames(new_val["message_typedef"], fieldnext.get(name)[int(key)-1], is_type)
            else:
                new_val = value
            new_json[xname] = new_val
            d+=1
        
    elif (type(js) == list):
        new_json = []
        x = 0
        for ix in js:
            d = 0
            tmp_new_json = {}
            for key, value in ix.items():
                xname = getKeyName(name, key)
                if (((type(value) == dict and (is_type == False or value["type"] == "message")) or (type(value) == list and len(value) > 0 and type(value[0]) == dict)) and fieldnext.get(name) != None and fieldnext.get(name)[int(key)-1] != None):
                    if (is_type == False):
                        new_val = ProtobufAddNames(value, fieldnext.get(name)[int(key)-1],is_type)
                    else:
                        new_val = value
                        new_val["message_typedef"] = ProtobufAddNames(new_val["message_typedef"], fieldnext.get(name)[int(key)-1],is_type)
                else:
                    new_val = value
                tmp_new_json[xname] = new_val
                d+=1
            new_json.append(tmp_new_json)
            x+=1
    return new_json
def ProtobufRemoveNames(js, name, is_type = False):
    if (type(js) == dict):
        new_json = {}
        d = 0
        for key, value in js.items():
            v = False
            try:
                xname = getKeyName(name, key)
                v = True
            except:
                xname = str(getKeyValue(name, key))
            if (((type(value) == dict and (is_type == False or value["type"] == "message")) or (type(value) == list and len(value) > 0 and type(value[0]) == dict)) and fieldnext.get(name) != None and ((v == True and fieldnext.get(name)[int(key)-1] != None) or (v == False and fieldnext.get(name)[int(xname)-1]))):
                if (is_type == False):
                    new_val = ProtobufRemoveNames(value, fieldnext.get(name)[int(xname)-1],is_type)
                else:
                    new_val = value
                    new_val["message_typedef"] = ProtobufRemoveNames(new_val["message_typedef"], fieldnext.get(name)[int(xname)-1],is_type)
            else:
                new_val = value
            new_json[xname] = new_val
            d+=1
        
    elif (type(js) == list):
        new_json = []
        x = 0
        for ix in js:
            d = 0
            tmp_new_json = {}
            for key, value in ix.items():
                v = False
                try:
                    xname = getKeyName(name, key)
                    v = True
                except:
                    xname = str(getKeyValue(name, key))
                if (((type(value) == dict and (is_type == False or value["type"] == "message")) or (type(value) == list and len(value) > 0 and type(value[0]) == dict)) and fieldnext.get(name) != None and ((v == True and fieldnext.get(name)[int(key)-1] != None) or (v == False and fieldnext.get(name)[int(xname)-1]))):
                    if (is_type == False):
                        new_val = ProtobufRemoveNames(value, fieldnext.get(name)[int(xname)-1],is_type)
                    else:
                        new_val = value
                        new_val["message_typedef"] = ProtobufRemoveNames(new_val["message_typedef"], fieldnext.get(name)[int(xname)-1],is_type)
                        
                else:
                    new_val = value
                tmp_new_json[xname] = new_val
                d+=1
            new_json.append(tmp_new_json)
            x+=1
    return new_json
