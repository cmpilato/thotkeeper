# Releasing ThotKeeper #

Primary development of ThotKeeper occurs on `master` branch.  We use
feature branches for larger things, but currently have no need for
published release branches.  At the moment, the general approach to
releases involves tagging a small variant of the current `master` and
blessing that as a release.

## Release Process ##

Ensure that copyright years are correct, and commit and push any
changes resulting from the process.

    > $ ./tools/bump-copyright-years .

Create a local release branch.

    > $ git checkout -b X.Y.Z-release

Update the `CHANGES` file, pegging the date of the release.

Update `lib/tk_main.py`, removing "-dev" from the `__version__`
variable value and establishing the desired final version.

Commit these changes.

    > $ git commit -a -m "Prepare for the X.Y.Z release"

Tag to release and push the tag upstream.

    > $ git tag -a -m "Tag the X.Y.Z release." X.Y.Z  
    > $ git push origin tag X.Y.Z

Build the release archives with the `make-release` script.

    > $ tools/make-release ~/Desktop X.Y.Z

Make sure that the generated files have the right stuff (and don't have the
wrong stuff).

Now, edit the GitHub release (at https://github.com/cmpilato/thotkeeper/releases/tag/X.Y.Z):

    * Change the release title to "ThotKeeper X.Y.Z"
 
    * Copy the `CHANGES` entries for the release into the description:

        ```
        ChangeLog:
         
          * Did some stuff.
          * Fixed some bugs.
         ```
         
    * Attach the release archive files (tar.gz and zip) to the release.

## After the Release ##

After releasing a new version, we need to make sure that `master` is ready to
continue on into the future.  So switch back to that branch.

    > $ git checkout master
  
Merge the changes you made on the release branch.

    > $ git merge X.Y.Z-release
        
Edit `lib/tk_main.py` to increment the patch number of the `__version__`
variable and re-add the "-dev" suffix.

Edit `CHANGES` and add the template for the next release's changes.

Commit and push these changes.

    > $ git commit -a -m "Begin a new release cycle."; git push

Finally, remove the release branch.

    > $ git branch -d X.Y.Z-release
