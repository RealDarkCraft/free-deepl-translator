from __future__ import annotations
from typing import Any, Dict, List, Optional


def getSendProperty() -> Dict[str, type]:
    return {
        "FieldEvent": FieldEvent,
        "AppendMessage": AppendMessage,
        "ParticipantRequest": ParticipantRequest,
    }


class FieldEvent:
    """Represents an event on a field in the DeepL document."""

    def __init__(
        self,
        fieldName: int,
        participantId: int,
        setPropertyOperation: Optional[Dict] = None,
        textChangeOperation: Optional[Dict] = None,
        removeAnnotationOperation: Optional[Dict] = None,
        createAnnotationOperation: Optional[Dict] = None,
    ):
        self.participantId = participantId
        self.fieldName = fieldName
        self.setPropertyOperation = setPropertyOperation
        self.textChangeOperation = textChangeOperation
        self.removeAnnotationOperation = removeAnnotationOperation
        self.createAnnotationOperation = createAnnotationOperation

    def toObj(self) -> Dict[str, Any]:
        ret: Dict[str, Any] = {
            "fieldName": self.fieldName,
            "participantId": {"value": self.participantId},
        }
        if self.setPropertyOperation is not None:
            ret["setPropertyOperation"] = self.setPropertyOperation
        if self.textChangeOperation is not None:
            ret["textChangeOperation"] = self.textChangeOperation
        if self.createAnnotationOperation is not None:
            ret["createAnnotationOperation"] = self.createAnnotationOperation
        if self.removeAnnotationOperation is not None:
            ret["removeAnnotationOperation"] = self.removeAnnotationOperation
        return ret


class AppendMessage:
    """Encapsulates a list of events with a base version."""

    def __init__(self, events: List[FieldEvent], baseVersion: int):
        self.events = events
        self.baseVersion = baseVersion

    def toObj(self) -> Dict[str, Any]:
        return {
            "events": [x.toObj() for x in self.events],
            "baseVersion": {"version": {"value": self.baseVersion}},
        }


class ParticipantRequest:
    """Participant request sent to the DeepL server."""

    def __init__(
        self,
        appendMessage: AppendMessage,
        updateAuthenticationTokenMessage: Optional[str] = None,
    ):
        self.appendMessage = appendMessage
        self.updateAuthenticationTokenMessage = updateAuthenticationTokenMessage

    def toObj(self) -> Dict[str, Any]:
        ret: Dict[str, Any] = {"appendMessage": self.appendMessage.toObj()}
        if self.updateAuthenticationTokenMessage is not None:
            ret["updateAuthenticationTokenMessage"] = str(
                self.updateAuthenticationTokenMessage
            )
        return ret
