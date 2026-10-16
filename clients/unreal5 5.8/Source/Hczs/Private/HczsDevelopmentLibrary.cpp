#include "HczsDevelopmentLibrary.h"
#if WITH_EDITOR
#include "Editor.h"
#include "Settings/LevelEditorPlaySettings.h"
#endif

bool UHczsDevelopmentLibrary::RequestFloatingPlaySession(int32 Width, int32 Height)
{
#if WITH_EDITOR
    if (!GEditor || GEditor->IsPlaySessionInProgress() || Width < 320 || Height < 240 || Width > 7680 || Height > 4320) return false;
    ULevelEditorPlaySettings* Settings = DuplicateObject(GetDefault<ULevelEditorPlaySettings>(), GetTransientPackage());
    Settings->LastExecutedPlayModeType = PlayMode_InEditorFloating;
    Settings->NewWindowWidth = Width;
    Settings->NewWindowHeight = Height;
    Settings->CenterNewWindow = true;
    FRequestPlaySessionParams Params;
    Params.WorldType = EPlaySessionWorldType::PlayInEditor;
    Params.EditorPlaySettings = Settings;
    GEditor->RequestPlaySession(Params);
    return true;
#else
    return false;
#endif
}
