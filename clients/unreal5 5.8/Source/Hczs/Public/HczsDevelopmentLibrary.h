#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "HczsDevelopmentLibrary.generated.h"

UCLASS()
class HCZS_API UHczsDevelopmentLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Editor-only: requests PIE in a floating window with the exact client size, for
     * aspect-dependent acceptance (the level viewport size depends on editor layout). */
    UFUNCTION(BlueprintCallable, Category = "Hczs|Development")
    static bool RequestFloatingPlaySession(int32 Width, int32 Height);
};
