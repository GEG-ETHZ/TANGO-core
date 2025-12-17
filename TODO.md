# TODO

- [ ] Investigate what it would take to have round trip symmetry in writing
      `tango.specs` to a yaml file.  Right now, merged defaults would be expanded (the
      common dict gets merged with unit-specific dicts), and it may be worth trying to
      change the way this works so that specs doesn't have any preprocessing relative
      to what comes in for the original file 
- [ ] cleanup how `addons_manager` works.
  - [ ] what does it even do?
  - [ ] it seems to make tango really sensitive to having the project directory have
        a very specific name: `TANGO`
  - [ ] ???
- [ ] make it so that `TANGO` can store all state variables and results in ArangoDB,
      along with specs and specs_hash
